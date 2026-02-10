from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from coordinator_core.entities.prediction import PredictionScore


class ScoreService:
    def __init__(
        self,
        checkpoint_interval_seconds: int,
        scoring_function: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        prediction_repository,
        model_repository,
        leaderboard_repository,
        model_score_aggregator: Callable[[list[Any], dict[str, Any]], list[dict[str, Any]]] | None,
        leaderboard_ranker: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None,
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.scoring_function = scoring_function
        self.prediction_repository = prediction_repository
        self.model_repository = model_repository
        self.leaderboard_repository = leaderboard_repository
        self.model_score_aggregator = model_score_aggregator
        self.leaderboard_ranker = leaderboard_ranker

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

            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.checkpoint_interval_seconds)
            except asyncio.TimeoutError:
                pass

    def run_once(self) -> bool:
        predictions = list(self.prediction_repository.fetch_ready_to_score())
        if not predictions:
            return False

        now = datetime.now(timezone.utc)

        for prediction in predictions:
            result = self.scoring_function(prediction.inference_output, {})

            prediction.score = PredictionScore(
                value=self._to_float(result.get("value")),
                success=bool(result.get("success", True)),
                failed_reason=result.get("failed_reason"),
                scored_at=now,
            )

        self.prediction_repository.save_all(predictions)
        self._rebuild_leaderboard(recent_predictions=predictions)
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
        if self.model_score_aggregator is not None:
            return list(self.model_score_aggregator(scored_predictions, models))

        by_model: dict[str, list[float]] = {}
        for prediction in scored_predictions:
            if prediction.score is None:
                continue
            if not prediction.score.success:
                continue
            if prediction.score.value is None:
                continue

            by_model.setdefault(prediction.model_id, []).append(float(prediction.score.value))

        entries: list[dict[str, Any]] = []
        for model_id, scores in by_model.items():
            if not scores:
                continue

            avg_score = sum(scores) / len(scores)
            model = models.get(model_id)

            entries.append(
                {
                    "model_id": model_id,
                    "score_recent": avg_score,
                    "score_steady": avg_score,
                    "score_anchor": avg_score,
                    "model_name": model.name if model else None,
                    "cruncher_name": model.player_name if model else None,
                }
            )

        return entries

    def _rank_leaderboard(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.leaderboard_ranker is not None:
            return list(self.leaderboard_ranker(entries))

        ranked_entries = sorted(entries, key=lambda entry: entry["score_anchor"], reverse=True)
        for idx, entry in enumerate(ranked_entries, start=1):
            entry["rank"] = idx
        return ranked_entries

    def _collect_scored_predictions(self, recent_predictions):
        if hasattr(self.prediction_repository, "fetch_scored_predictions"):
            return list(self.prediction_repository.fetch_scored_predictions())
        return list(recent_predictions)

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None
