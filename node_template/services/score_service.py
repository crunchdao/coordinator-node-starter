"""Score service: resolve actuals → score predictions → save scores → rebuild leaderboard."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from coordinator_core.entities.prediction import ScoreRecord
from coordinator_core.schemas import LeaderboardEntryEnvelope, ScoreEnvelope
from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from coordinator_core.services.interfaces.prediction_repository import PredictionRepository
from coordinator_core.services.interfaces.score_repository import ScoreRepository
from node_template.contracts import CrunchContract
from node_template.services.input_service import InputService


class ScoreService:
    def __init__(
        self,
        checkpoint_interval_seconds: int,
        scoring_function: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        input_service: InputService | None = None,
        prediction_repository: PredictionRepository | None = None,
        score_repository: ScoreRepository | None = None,
        model_repository: ModelRepository | None = None,
        leaderboard_repository: LeaderboardRepository | None = None,
        contract: CrunchContract | None = None,
        **kwargs,
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.scoring_function = scoring_function
        self.input_service = input_service
        self.prediction_repository = prediction_repository
        self.score_repository = score_repository
        self.model_repository = model_repository
        self.leaderboard_repository = leaderboard_repository
        self.contract = contract or CrunchContract()

        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self.logger.info("score service started")
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception("score loop error: %s", exc)
                self._rollback_repositories()
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.checkpoint_interval_seconds)
            except asyncio.TimeoutError:
                pass

    def run_once(self) -> bool:
        now = datetime.now(timezone.utc)

        # 1. resolve actuals for predictions past their horizon
        self._resolve_actuals(now)

        # 2. score predictions that have actuals
        scored = self._score_predictions(now)
        if not scored:
            self.logger.info("No predictions scored this cycle")
            return False

        # 3. rebuild leaderboard
        self._rebuild_leaderboard()
        return True

    async def shutdown(self) -> None:
        self.stop_event.set()

    # ── 1. resolve actuals ──

    def _resolve_actuals(self, now: datetime) -> int:
        pending = self.prediction_repository.find(
            status="PENDING", resolvable_before=now,
        )
        if not pending:
            return 0

        resolved = 0
        for prediction in pending:
            if self.input_service is None:
                continue

            scope = prediction.scope or {}
            actuals = self.input_service.get_ground_truth(
                performed_at=prediction.performed_at,
                resolvable_at=prediction.resolvable_at,
                asset=scope.get("asset"),
            )
            if actuals is None:
                continue

            # Save a score record with actuals but no score yet
            if self.score_repository is not None:
                self.score_repository.save(ScoreRecord(
                    id=f"SCR_{prediction.id}",
                    prediction_id=prediction.id,
                    actuals=actuals,
                    value=None, success=True, failed_reason=None,
                    scored_at=now,
                ))

            # Mark prediction as resolved
            prediction.status = "RESOLVED"
            self.prediction_repository.save(prediction)
            resolved += 1

        if resolved:
            self.logger.info("Resolved actuals for %d predictions", resolved)
        return resolved

    # ── 2. score predictions ──

    def _score_predictions(self, now: datetime) -> list[ScoreRecord]:
        predictions = self.prediction_repository.find(status="RESOLVED")
        if not predictions:
            return []

        scored: list[ScoreRecord] = []
        for prediction in predictions:
            # Get actuals from score record
            actuals = self._get_actuals(prediction.id)
            if actuals is None:
                continue

            result = self.scoring_function(prediction.inference_output, actuals)
            validated = self.contract.score_type(**result)

            score = ScoreRecord(
                id=f"SCR_{prediction.id}",
                prediction_id=prediction.id,
                actuals=actuals,
                value=validated.value,
                success=validated.success,
                failed_reason=validated.failed_reason,
                scored_at=now,
            )

            if self.score_repository is not None:
                self.score_repository.save(score)

            prediction.status = "SCORED"
            self.prediction_repository.save(prediction)
            scored.append(score)

        if scored:
            self.logger.info("Scored %d predictions", len(scored))
        return scored

    def _get_actuals(self, prediction_id: str) -> dict[str, Any] | None:
        if self.score_repository is None:
            return None
        records = self.score_repository.find(prediction_id=prediction_id, limit=1)
        if records and records[0].actuals:
            return records[0].actuals
        return None

    # ── 3. leaderboard ──

    def _rebuild_leaderboard(self) -> None:
        scores = self.score_repository.find() if self.score_repository else []
        models = self.model_repository.fetch_all()

        # Build prediction_id → score mapping
        score_by_pred: dict[str, ScoreRecord] = {}
        for s in scores:
            if s.value is not None and s.success:
                score_by_pred[s.prediction_id] = s

        # Get all scored predictions for timestamps and model_ids
        scored_predictions = self.prediction_repository.find(status="SCORED")

        aggregated = self._aggregate(scored_predictions, score_by_pred, models)
        ranked = self._rank(aggregated)

        self.leaderboard_repository.save(
            ranked, meta={"generated_by": "node_template.score_service"},
        )

    def _aggregate(self, predictions, score_by_pred, models) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        aggregation = self.contract.aggregation

        by_model: dict[str, list[tuple[datetime, float]]] = {}
        for pred in predictions:
            score = score_by_pred.get(pred.id)
            if score is None:
                continue
            by_model.setdefault(pred.model_id, []).append(
                (pred.performed_at, float(score.value))
            )

        entries: list[dict[str, Any]] = []
        for model_id, timed_scores in by_model.items():
            metrics: dict[str, float] = {}
            for name, window in aggregation.windows.items():
                cutoff = now - timedelta(hours=window.hours)
                vals = [v for ts, v in timed_scores if ts >= cutoff]
                metrics[name] = sum(vals) / len(vals) if vals else 0.0

            model = models.get(model_id)
            entries.append(LeaderboardEntryEnvelope(
                model_id=model_id,
                score=ScoreEnvelope(
                    metrics=metrics,
                    ranking={"key": aggregation.ranking_key,
                             "value": metrics.get(aggregation.ranking_key, 0.0),
                             "direction": aggregation.ranking_direction},
                    payload={},
                ),
                model_name=model.name if model else None,
                cruncher_name=model.player_name if model else None,
            ).model_dump(exclude_none=True))

        return entries

    def _rank(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        key = self.contract.aggregation.ranking_key
        reverse = self.contract.aggregation.ranking_direction == "desc"

        def sort_key(e):
            score = e.get("score")
            if not isinstance(score, dict):
                return float("-inf")
            try:
                return float((score.get("metrics") or {}).get(key, 0.0))
            except Exception:
                return float("-inf")

        ranked = sorted(entries, key=sort_key, reverse=reverse)
        for idx, entry in enumerate(ranked, start=1):
            entry["rank"] = idx
        return ranked

    # keep old name for test compat
    _rank_leaderboard = _rank

    def _rollback_repositories(self) -> None:
        for name, repo in [("prediction", self.prediction_repository),
                           ("score", self.score_repository),
                           ("model", self.model_repository),
                           ("leaderboard", self.leaderboard_repository)]:
            rollback = getattr(repo, "rollback", None)
            if callable(rollback):
                try:
                    rollback()
                except Exception as exc:
                    self.logger.warning("Rollback failed for %s: %s", name, exc)
