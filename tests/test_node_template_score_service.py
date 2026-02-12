from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord
from node_template.contracts import Aggregation, AggregationWindow, CrunchContract
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


class RollbackPredictionRepository(InMemoryPredictionRepository):
    def __init__(self):
        super().__init__(predictions=[])
        self.rollback_calls = 0

    def rollback(self):
        self.rollback_calls += 1


class RollbackModelRepository(InMemoryModelRepository):
    def __init__(self):
        super().__init__()
        self.rollback_calls = 0

    def rollback(self):
        self.rollback_calls += 1


class RollbackLeaderboardRepository(InMemoryLeaderboardRepository):
    def __init__(self):
        super().__init__()
        self.rollback_calls = 0

    def rollback(self):
        self.rollback_calls += 1


class TestNodeTemplateScoreService(unittest.TestCase):
    def test_run_once_scores_and_builds_leaderboard(self):
        prediction = PredictionRecord(
            id="pre-1",
            model_id="m1",
            prediction_config_id="CFG_1",
            scope_key="BTC-60",
            scope={"asset": "BTC", "horizon": 60, "step": 60},
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

        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda prediction, ground_truth: {"value": 0.5, "success": True, "failed_reason": None},
            prediction_repository=prediction_repo,
            model_repository=model_repo,
            leaderboard_repository=leaderboard_repo,
            ground_truth_resolver=lambda prediction: {"y_up": True},
            contract=CrunchContract(),
        )

        changed = service.run_once()

        self.assertTrue(changed)
        self.assertEqual(len(prediction_repo.saved_predictions), 1)
        self.assertIsNotNone(prediction_repo.saved_predictions[0].score)
        self.assertIsNotNone(leaderboard_repo.latest)
        self.assertEqual(leaderboard_repo.latest["entries"][0]["model_id"], "m1")
        self.assertEqual(leaderboard_repo.latest["entries"][0]["rank"], 1)
        self.assertEqual(leaderboard_repo.latest["entries"][0]["score"]["ranking"]["key"], "score_recent")
        self.assertIn("score_recent", leaderboard_repo.latest["entries"][0]["score"]["metrics"])

    def test_run_once_skips_predictions_without_ground_truth(self):
        prediction = PredictionRecord(
            id="pre-1",
            model_id="m1",
            prediction_config_id="CFG_1",
            scope_key="BTC-60",
            scope={"asset": "BTC", "horizon": 60, "step": 60},
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

    def test_rank_leaderboard_honors_ascending_ranking_direction(self):
        prediction_repo = InMemoryPredictionRepository([])
        model_repo = InMemoryModelRepository()
        leaderboard_repo = InMemoryLeaderboardRepository()

        asc_contract = CrunchContract(
            aggregation=Aggregation(
                windows={"loss": AggregationWindow(hours=24)},
                ranking_key="loss",
                ranking_direction="asc",
            )
        )

        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda prediction, ground_truth: {"value": 0.5, "success": True, "failed_reason": None},
            prediction_repository=prediction_repo,
            model_repository=model_repo,
            leaderboard_repository=leaderboard_repo,
            ground_truth_resolver=lambda prediction: {"y_up": True},
            contract=asc_contract,
        )

        ranked = service._rank_leaderboard(
            [
                {
                    "model_id": "m1",
                    "score": {
                        "metrics": {"loss": 0.4},
                        "ranking": {"key": "loss", "direction": "asc"},
                        "payload": {},
                    },
                },
                {
                    "model_id": "m2",
                    "score": {
                        "metrics": {"loss": 0.2},
                        "ranking": {"key": "loss", "direction": "asc"},
                        "payload": {},
                    },
                },
            ]
        )

        self.assertEqual([entry["model_id"] for entry in ranked], ["m2", "m1"])
        self.assertEqual([entry["rank"] for entry in ranked], [1, 2])


class TestNodeTemplateScoreServiceRunLoop(unittest.IsolatedAsyncioTestCase):
    async def test_run_rolls_back_repositories_after_loop_exception(self):
        prediction_repo = RollbackPredictionRepository()
        model_repo = RollbackModelRepository()
        leaderboard_repo = RollbackLeaderboardRepository()

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

        def boom_once():
            service.stop_event.set()
            raise RuntimeError("boom")

        service.run_once = boom_once  # type: ignore[method-assign]

        with self.assertLogs("node_template.services.score_service", level="ERROR"):
            await service.run()

        self.assertEqual(prediction_repo.rollback_calls, 1)
        self.assertEqual(model_repo.rollback_calls, 1)
        self.assertEqual(leaderboard_repo.rollback_calls, 1)


if __name__ == "__main__":
    unittest.main()
