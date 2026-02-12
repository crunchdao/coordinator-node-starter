"""Score service: resolve actuals on inputs → score predictions → leaderboard."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from coordinator.entities.prediction import ScoreRecord
from coordinator.schemas import LeaderboardEntryEnvelope, ScoreEnvelope
from coordinator.interfaces.input_repository import InputRepository
from coordinator.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator.interfaces.model_repository import ModelRepository
from coordinator.interfaces.prediction_repository import PredictionRepository
from coordinator.interfaces.score_repository import ScoreRepository
from coordinator.contracts import CrunchContract
from coordinator.services.input import InputService


class ScoreService:
    def __init__(
        self,
        checkpoint_interval_seconds: int,
        scoring_function: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        input_service: InputService | None = None,
        input_repository: InputRepository | None = None,
        prediction_repository: PredictionRepository | None = None,
        score_repository: ScoreRepository | None = None,
        model_repository: ModelRepository | None = None,
        leaderboard_repository: LeaderboardRepository | None = None,
        contract: CrunchContract | None = None,
        **kwargs: Any,
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.scoring_function = scoring_function
        self.input_service = input_service
        self.input_repository = input_repository
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

        # 1. resolve actuals on inputs past their horizon
        self._resolve_inputs(now)

        # 2. score predictions whose input has actuals
        scored = self._score_predictions(now)
        if not scored:
            self.logger.info("No predictions scored this cycle")
            return False

        # 3. rebuild leaderboard
        self._rebuild_leaderboard()
        return True

    async def shutdown(self) -> None:
        self.stop_event.set()

    # ── 1. resolve actuals on inputs ──

    def _resolve_inputs(self, now: datetime) -> int:
        if self.input_repository is None or self.input_service is None:
            return 0

        unresolved = self.input_repository.find(
            status="RECEIVED", resolvable_before=now,
        )
        if not unresolved:
            return 0

        resolved = 0
        for inp in unresolved:
            actuals = self.input_service.get_ground_truth(
                performed_at=inp.received_at,
                resolvable_at=inp.resolvable_at,
                asset=inp.scope.get("asset"),
            )
            if actuals is None:
                continue

            inp.actuals = actuals
            inp.status = "RESOLVED"
            self.input_repository.save(inp)
            resolved += 1

        if resolved:
            self.logger.info("Resolved actuals for %d inputs", resolved)
        return resolved

    # ── 2. score predictions ──

    def _score_predictions(self, now: datetime) -> list[ScoreRecord]:
        predictions = self.prediction_repository.find(status="PENDING")
        if not predictions:
            return []

        # Build input lookup for actuals
        input_ids = {p.input_id for p in predictions}
        inputs_by_id: dict[str, Any] = {}
        if self.input_repository is not None:
            for inp in self.input_repository.find(status="RESOLVED"):
                if inp.id in input_ids:
                    inputs_by_id[inp.id] = inp

        scored: list[ScoreRecord] = []
        for prediction in predictions:
            inp = inputs_by_id.get(prediction.input_id)
            if inp is None or inp.actuals is None:
                continue  # actuals not yet available

            result = self.scoring_function(prediction.inference_output, inp.actuals)
            validated = self.contract.score_type(**result)

            score = ScoreRecord(
                id=f"SCR_{prediction.id}",
                prediction_id=prediction.id,
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

    # ── 3. leaderboard ──

    def _rebuild_leaderboard(self) -> None:
        scores = self.score_repository.find() if self.score_repository else []
        models = self.model_repository.fetch_all()

        score_by_pred: dict[str, ScoreRecord] = {}
        for s in scores:
            if s.value is not None and s.success:
                score_by_pred[s.prediction_id] = s

        scored_predictions = self.prediction_repository.find(status="SCORED")
        aggregated = self._aggregate(scored_predictions, score_by_pred, models)
        ranked = self._rank(aggregated)

        self.leaderboard_repository.save(
            ranked, meta={"generated_by": "coordinator.score_service"},
        )

    def _aggregate(self, predictions: Any, score_by_pred: dict, models: dict) -> list[dict[str, Any]]:
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

        def sort_key(e: dict[str, Any]) -> float:
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

    _rank_leaderboard = _rank

    def _rollback_repositories(self) -> None:
        for name, repo in [("input", self.input_repository),
                           ("prediction", self.prediction_repository),
                           ("score", self.score_repository),
                           ("model", self.model_repository),
                           ("leaderboard", self.leaderboard_repository)]:
            rollback = getattr(repo, "rollback", None)
            if callable(rollback):
                try:
                    rollback()
                except Exception as exc:
                    self.logger.warning("Rollback failed for %s: %s", name, exc)
