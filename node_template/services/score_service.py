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
        ground_truth_resolver: Callable[[Any], dict[str, Any] | None] | None,
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.scoring_function = scoring_function
        self.prediction_repository = prediction_repository
        self.model_repository = model_repository
        self.leaderboard_repository = leaderboard_repository
        self.model_score_aggregator = model_score_aggregator
        self.leaderboard_ranker = leaderboard_ranker
        self.ground_truth_resolver = ground_truth_resolver

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
        predictions = list(self.prediction_repository.fetch_ready_to_score())
        if not predictions:
            self.logger.info("No predictions ready to score")
            return False

        now = datetime.now(timezone.utc)
        scored_predictions = []

        for prediction in predictions:
            ground_truth = self._resolve_ground_truth(prediction)
            if ground_truth is None:
                continue

            result = self.scoring_function(prediction.inference_output, ground_truth)

            prediction.score = PredictionScore(
                value=self._to_float(result.get("value")),
                success=bool(result.get("success", True)),
                failed_reason=result.get("failed_reason"),
                scored_at=now,
            )
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

    def _resolve_ground_truth(self, prediction) -> dict[str, Any] | None:
        if self.ground_truth_resolver is None:
            return {}

        truth = self.ground_truth_resolver(prediction)
        if truth is None:
            return None
        if not isinstance(truth, dict):
            raise ValueError("ground_truth_resolver must return a dictionary or None")
        return truth

    def _aggregate_model_scores(self, scored_predictions, models) -> list[dict[str, Any]]:
        if self.model_score_aggregator is not None:
            return [self._normalize_score_entry(entry) for entry in self.model_score_aggregator(scored_predictions, models)]

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
                    "score": {
                        "windows": {
                            "recent": avg_score,
                            "steady": avg_score,
                            "anchor": avg_score,
                        },
                        "rank_key": avg_score,
                        "payload": {},
                    },
                    "model_name": model.name if model else None,
                    "cruncher_name": model.player_name if model else None,
                }
            )

        return [self._normalize_score_entry(entry) for entry in entries]

    def _rank_leaderboard(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.leaderboard_ranker is not None:
            return list(self.leaderboard_ranker(entries))

        ranked_entries = sorted(entries, key=self._entry_rank_value, reverse=True)
        for idx, entry in enumerate(ranked_entries, start=1):
            entry["rank"] = idx
        return ranked_entries

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

    @staticmethod
    def _normalize_score_entry(entry: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise ValueError("Model score aggregator entries must be dictionaries")

        score = entry.get("score")
        if isinstance(score, dict):
            windows = score.get("windows") if isinstance(score.get("windows"), dict) else {}
            rank_key = score.get("rank_key")
            payload = score.get("payload") if isinstance(score.get("payload"), dict) else {}
            return {
                **entry,
                "score": {
                    "windows": windows,
                    "rank_key": rank_key,
                    "payload": payload,
                },
            }

        windows = {
            "recent": entry.get("score_recent"),
            "steady": entry.get("score_steady"),
            "anchor": entry.get("score_anchor"),
        }
        rank_key = entry.get("rank_key", entry.get("score_anchor"))
        return {
            **entry,
            "score": {
                "windows": windows,
                "rank_key": rank_key,
                "payload": {},
            },
        }

    @classmethod
    def _entry_rank_value(cls, entry: dict[str, Any]) -> float:
        score = entry.get("score") if isinstance(entry, dict) else None
        if isinstance(score, dict):
            rank_key = score.get("rank_key")
            if rank_key is not None:
                try:
                    return float(rank_key)
                except Exception:
                    pass

            windows = score.get("windows") if isinstance(score.get("windows"), dict) else {}
            anchor = windows.get("anchor")
            if anchor is not None:
                try:
                    return float(anchor)
                except Exception:
                    pass

        fallback = entry.get("score_anchor") if isinstance(entry, dict) else None
        if fallback is not None:
            try:
                return float(fallback)
            except Exception:
                pass

        return float("-inf")

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None
