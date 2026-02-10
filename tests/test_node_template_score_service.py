from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord
from node_template.services.score_service import ScoreService


class InMemoryPredictionRepository:
    def __init__(self, predictions):
        self.predictions = predictions
        self.saved_predictions = []

    def fetch_ready_to_score(self):
        return self.predictions

    def save(self, prediction):
        self.saved_predictions.append(prediction)

    def save_all(self, predictions):
        self.saved_predictions.extend(list(predictions))

    def fetch_scored_predictions(self):
        return [p for p in self.saved_predictions if p.score is not None]


class InMemoryModelRepository:
    def __init__(self):
        self.models = {
            "m1": Model(
                id="m1",
                name="model-one",
                player_id="p1",
                player_name="alice",
                deployment_identifier="d1",
            )
        }

    def fetch_all(self):
        return self.models

    def fetch_by_ids(self, ids):
        return {k: v for k, v in self.models.items() if k in ids}

    def fetch(self, model_id):
        return self.models.get(model_id)

    def save(self, model):
        self.models[model.id] = model

    def save_all(self, models):
        for model in models:
            self.save(model)


class InMemoryLeaderboardRepository:
    def __init__(self):
        self.latest = None

    def save(self, leaderboard_entries, meta=None):
        self.latest = {"entries": leaderboard_entries, "meta": meta or {}}

    def get_latest(self):
        return self.latest


class TestNodeTemplateScoreService(unittest.TestCase):
    def test_run_once_scores_and_builds_leaderboard(self):
        prediction = PredictionRecord(
            id="pre-1",
            model_id="m1",
            asset="BTC",
            horizon=60,
            step=60,
            status="SUCCESS",
            exec_time_ms=10.0,
            inference_input={"x": 1},
            inference_output={"distribution": []},
            performed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            resolvable_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        prediction_repo = InMemoryPredictionRepository([prediction])
        model_repo = InMemoryModelRepository()
        leaderboard_repo = InMemoryLeaderboardRepository()

        def model_score_aggregator(scored_predictions, models):
            self.assertEqual(len(scored_predictions), 1)
            self.assertIn("m1", models)
            return [
                {
                    "model_id": "m1",
                    "score_recent": 123.0,
                    "score_steady": 123.0,
                    "score_anchor": 123.0,
                    "model_name": "model-one",
                    "cruncher_name": "alice",
                }
            ]

        def leaderboard_ranker(entries):
            return [
                {
                    **entry,
                    "rank": 7,
                }
                for entry in entries
            ]

        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda prediction, ground_truth: {"value": 0.5, "success": True, "failed_reason": None},
            prediction_repository=prediction_repo,
            model_repository=model_repo,
            leaderboard_repository=leaderboard_repo,
            model_score_aggregator=model_score_aggregator,
            leaderboard_ranker=leaderboard_ranker,
            ground_truth_resolver=lambda prediction: {"y_up": True},
        )

        changed = service.run_once()

        self.assertTrue(changed)
        self.assertEqual(len(prediction_repo.saved_predictions), 1)
        self.assertIsNotNone(prediction_repo.saved_predictions[0].score)
        self.assertIsNotNone(leaderboard_repo.latest)
        self.assertEqual(leaderboard_repo.latest["entries"][0]["model_id"], "m1")
        self.assertEqual(leaderboard_repo.latest["entries"][0]["rank"], 7)
        self.assertEqual(leaderboard_repo.latest["entries"][0]["score_anchor"], 123.0)

    def test_run_once_skips_predictions_without_ground_truth(self):
        prediction = PredictionRecord(
            id="pre-1",
            model_id="m1",
            asset="BTC",
            horizon=60,
            step=60,
            status="SUCCESS",
            exec_time_ms=10.0,
            inference_input={"x": 1},
            inference_output={"p_up": 0.5},
            performed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            resolvable_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        prediction_repo = InMemoryPredictionRepository([prediction])
        model_repo = InMemoryModelRepository()
        leaderboard_repo = InMemoryLeaderboardRepository()

        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda prediction, ground_truth: {"value": 0.5, "success": True, "failed_reason": None},
            prediction_repository=prediction_repo,
            model_repository=model_repo,
            leaderboard_repository=leaderboard_repo,
            model_score_aggregator=lambda scored_predictions, models: [],
            leaderboard_ranker=lambda entries: entries,
            ground_truth_resolver=lambda prediction: None,
        )

        changed = service.run_once()

        self.assertFalse(changed)
        self.assertEqual(len(prediction_repo.saved_predictions), 0)
        self.assertIsNone(leaderboard_repo.latest)

    def test_run_once_logs_when_no_predictions_ready(self):
        prediction_repo = InMemoryPredictionRepository([])
        model_repo = InMemoryModelRepository()
        leaderboard_repo = InMemoryLeaderboardRepository()

        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda prediction, ground_truth: {"value": 0.5, "success": True, "failed_reason": None},
            prediction_repository=prediction_repo,
            model_repository=model_repo,
            leaderboard_repository=leaderboard_repo,
            model_score_aggregator=lambda scored_predictions, models: [],
            leaderboard_ranker=lambda entries: entries,
            ground_truth_resolver=lambda prediction: {"y_up": True},
        )

        with self.assertLogs("node_template.services.score_service", level="INFO") as logs:
            changed = service.run_once()

        self.assertFalse(changed)
        self.assertTrue(any("No predictions ready to score" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
