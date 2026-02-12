from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from coordinator_core.entities.prediction import PredictionScore
from coordinator_core.schemas import LeaderboardEntryEnvelope, ScoreEnvelope
from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from coordinator_core.services.interfaces.prediction_repository import PredictionRepository
from node_template.contracts import CrunchContract


class ScoreService:
    def __init__(
        self,
        checkpoint_interval_seconds: int,
        scoring_function: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        prediction_repository: PredictionRepository | None = None,
        model_repository: ModelRepository | None = None,
        leaderboard_repository: LeaderboardRepository | None = None,
        contract: CrunchContract | None = None,
        **kwargs,
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.scoring_function = scoring_function
        self.prediction_repository = prediction_repository
        self.model_repository = model_repository
        self.leaderboard_repository = leaderboard_repository
        self.contract = contract or CrunchContract()

        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self.logger.info("node_template score service started")

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
        predictions = self.prediction_repository.find_predictions(status="RESOLVED")
        if not predictions:
            self.logger.info("No predictions ready to score")
            return False

        now = datetime.now(timezone.utc)
        scored_predictions = []

        for prediction in predictions:
            actuals = prediction.actuals
            if actuals is None:
                continue

            result = self.scoring_function(prediction.inference_output, actuals)

            # Validate score via contract type
            validated = self.contract.score_type(**result)

            prediction.score = PredictionScore(
                value=validated.value,
                success=validated.success,
                failed_reason=validated.failed_reason,
                scored_at=now,
            )
            prediction.status = "SCORED"
            scored_predictions.append(prediction)

        if not scored_predictions:
            self.logger.info("No predictions were scored in this cycle")
            return False

        self.prediction_repository.save_all(scored_predictions)
        self.logger.info("Scored %d predictions", len(scored_predictions))
        self._rebuild_leaderboard(recent_predictions=scored_predictions)
        return True

    async def shutdown(self) -> None:
        self.stop_event.set()

    def _rebuild_leaderboard(self, recent_predictions) -> None:
        scored_predictions = self._collect_scored_predictions(recent_predictions)
        models = self.model_repository.fetch_all()

        aggregated_entries = self._aggregate_model_scores(scored_predictions, models)
        ranked_entries = self._rank_leaderboard(aggregated_entries)

        self.leaderboard_repository.save(
            ranked_entries,
            meta={"generated_by": "node_template.score_service"},
        )

    def _aggregate_model_scores(self, scored_predictions, models) -> list[dict[str, Any]]:
        """Aggregate scores per model using contract-defined time windows."""
        now = datetime.now(timezone.utc)
        aggregation = self.contract.aggregation

        # Group scores by model with timestamps
        by_model: dict[str, list[tuple[datetime, float]]] = {}
        for prediction in scored_predictions:
            if prediction.score is None or not prediction.score.success or prediction.score.value is None:
                continue
            by_model.setdefault(str(prediction.model_id), []).append(
                (prediction.performed_at, float(prediction.score.value))
            )

        entries: list[dict[str, Any]] = []
        for model_id, timed_scores in by_model.items():
            if not timed_scores:
                continue

            # Compute each window metric
            metrics: dict[str, float] = {}
            for window_name, window in aggregation.windows.items():
                cutoff = now - timedelta(hours=window.hours)
                window_scores = [v for ts, v in timed_scores if ts >= cutoff]
                metrics[window_name] = (
                    sum(window_scores) / len(window_scores) if window_scores else 0.0
                )

            ranking_value = metrics.get(aggregation.ranking_key, 0.0)
            model = models.get(model_id)

            score_envelope = ScoreEnvelope(
                metrics=metrics,
                ranking={
                    "key": aggregation.ranking_key,
                    "value": ranking_value,
                    "direction": aggregation.ranking_direction,
                },
                payload={},
            )
            entry_envelope = LeaderboardEntryEnvelope(
                model_id=model_id,
                score=score_envelope,
                model_name=model.name if model else None,
                cruncher_name=model.player_name if model else None,
            )
            entries.append(entry_envelope.model_dump(exclude_none=True))

        return entries

    def _rank_leaderboard(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rank leaderboard using contract-defined ranking key and direction."""
        aggregation = self.contract.aggregation
        reverse = aggregation.ranking_direction == "desc"

        def sort_key(entry: dict[str, Any]) -> float:
            score = entry.get("score")
            if not isinstance(score, dict):
                return float("-inf")
            metrics = score.get("metrics") or {}
            try:
                return float(metrics.get(aggregation.ranking_key, 0.0))
            except Exception:
                return float("-inf")

        ranked = sorted(entries, key=sort_key, reverse=reverse)
        for idx, entry in enumerate(ranked, start=1):
            entry["rank"] = idx
        return ranked

    def _collect_scored_predictions(self, recent_predictions):
        if hasattr(self.prediction_repository, "fetch_scored_predictions"):
            return list(self.prediction_repository.fetch_scored_predictions())
        return list(recent_predictions)

    def _rollback_repositories(self) -> None:
        repositories = [
            ("prediction", self.prediction_repository),
            ("model", self.model_repository),
            ("leaderboard", self.leaderboard_repository),
        ]

        for repo_name, repository in repositories:
            rollback = getattr(repository, "rollback", None)
            if not callable(rollback):
                continue

            try:
                rollback()
            except Exception as exc:
                self.logger.warning("Rollback failed for %s repository: %s", repo_name, exc)
