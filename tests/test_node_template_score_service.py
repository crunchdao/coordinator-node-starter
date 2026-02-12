from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord, PredictionScore, ScoreRecord
from node_template.contracts import Aggregation, AggregationWindow, CrunchContract
from node_template.services.score_service import ScoreService


class InMemoryPredictionRepository:
    def __init__(self, predictions):
        self._predictions = list(predictions)

    def find(self, *, status=None, resolvable_before=None, **kwargs):
        results = list(self._predictions)
        if status is not None:
            if isinstance(status, list):
                results = [p for p in results if p.status in status]
            else:
                results = [p for p in results if p.status == status]
        if resolvable_before is not None:
            results = [p for p in results if p.resolvable_at and p.resolvable_at <= resolvable_before]
        return results

    def save(self, prediction):
        for i, p in enumerate(self._predictions):
            if p.id == prediction.id:
                self._predictions[i] = prediction
                return
        self._predictions.append(prediction)

    def save_all(self, predictions):
        for p in predictions:
            self.save(p)


class InMemoryScoreRepository:
    def __init__(self):
        self.scores: list[ScoreRecord] = []

    def save(self, record):
        for i, s in enumerate(self.scores):
            if s.id == record.id:
                self.scores[i] = record
                return
        self.scores.append(record)

    def find(self, *, prediction_id=None, model_id=None, since=None, until=None, limit=None):
        results = list(self.scores)
        if prediction_id is not None:
            results = [s for s in results if s.prediction_id == prediction_id]
        if limit is not None:
            results = results[:limit]
        return results


class InMemoryModelRepository:
    def __init__(self):
        self.models = {
            "m1": Model(id="m1", name="model-one", player_id="p1",
                        player_name="alice", deployment_identifier="d1")
        }

    def fetch_all(self):
        return self.models


class InMemoryLeaderboardRepository:
    def __init__(self):
        self.latest = None

    def save(self, entries, meta=None):
        self.latest = {"entries": entries, "meta": meta or {}}

    def get_latest(self):
        return self.latest


class FakeInputService:
    def __init__(self, actuals=None):
        self._actuals = actuals

    def get_ground_truth(self, performed_at, resolvable_at, asset=None):
        return self._actuals


class RollbackPredictionRepository(InMemoryPredictionRepository):
    def __init__(self):
        super().__init__([])
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


def _make_prediction(status="PENDING", actuals=None):
    now = datetime.now(timezone.utc)
    return PredictionRecord(
        id="pre-1", input_id="inp-1", model_id="m1",
        prediction_config_id="CFG_1",
        scope_key="BTC-60", scope={"asset": "BTC", "horizon": 60},
        status=status, exec_time_ms=10.0,
        inference_output={"distribution": []},
        performed_at=now - timedelta(minutes=2),
        resolvable_at=now - timedelta(minutes=1),
    )


class TestNodeTemplateScoreService(unittest.TestCase):
    def test_run_once_resolves_actuals_and_scores(self):
        prediction = _make_prediction(status="PENDING")
        pred_repo = InMemoryPredictionRepository([prediction])
        score_repo = InMemoryScoreRepository()

        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda pred, actuals: {"value": 0.5, "success": True, "failed_reason": None},
            input_service=FakeInputService(actuals={"y_up": True}),
            prediction_repository=pred_repo,
            score_repository=score_repo,
            model_repository=InMemoryModelRepository(),
            leaderboard_repository=InMemoryLeaderboardRepository(),
        )

        changed = service.run_once()

        self.assertTrue(changed)
        self.assertEqual(len(score_repo.scores), 1)
        self.assertEqual(score_repo.scores[0].value, 0.5)
        # Prediction should be SCORED
        scored = pred_repo.find(status="SCORED")
        self.assertEqual(len(scored), 1)

    def test_run_once_skips_when_no_actuals(self):
        prediction = _make_prediction(status="PENDING")
        pred_repo = InMemoryPredictionRepository([prediction])
        score_repo = InMemoryScoreRepository()

        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda pred, actuals: {"value": 0.5, "success": True, "failed_reason": None},
            input_service=FakeInputService(actuals=None),
            prediction_repository=pred_repo,
            score_repository=score_repo,
            model_repository=InMemoryModelRepository(),
            leaderboard_repository=InMemoryLeaderboardRepository(),
        )

        changed = service.run_once()

        self.assertFalse(changed)
        self.assertEqual(len(score_repo.scores), 0)

    def test_run_once_logs_when_no_predictions(self):
        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda pred, actuals: {"value": 0.5, "success": True, "failed_reason": None},
            prediction_repository=InMemoryPredictionRepository([]),
            score_repository=InMemoryScoreRepository(),
            model_repository=InMemoryModelRepository(),
            leaderboard_repository=InMemoryLeaderboardRepository(),
        )

        with self.assertLogs("node_template.services.score_service", level="INFO") as logs:
            changed = service.run_once()

        self.assertFalse(changed)
        self.assertTrue(any("No predictions scored" in line for line in logs.output))

    def test_rank_leaderboard_honors_ascending(self):
        asc_contract = CrunchContract(
            aggregation=Aggregation(
                windows={"loss": AggregationWindow(hours=24)},
                ranking_key="loss", ranking_direction="asc",
            )
        )
        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda p, a: {},
            prediction_repository=InMemoryPredictionRepository([]),
            score_repository=InMemoryScoreRepository(),
            model_repository=InMemoryModelRepository(),
            leaderboard_repository=InMemoryLeaderboardRepository(),
            contract=asc_contract,
        )

        ranked = service._rank_leaderboard([
            {"model_id": "m1", "score": {"metrics": {"loss": 0.4}, "ranking": {}, "payload": {}}},
            {"model_id": "m2", "score": {"metrics": {"loss": 0.2}, "ranking": {}, "payload": {}}},
        ])
        self.assertEqual([e["model_id"] for e in ranked], ["m2", "m1"])
        self.assertEqual([e["rank"] for e in ranked], [1, 2])


class TestNodeTemplateScoreServiceRunLoop(unittest.IsolatedAsyncioTestCase):
    async def test_run_rolls_back_after_exception(self):
        pred_repo = RollbackPredictionRepository()
        model_repo = RollbackModelRepository()
        lb_repo = RollbackLeaderboardRepository()

        service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=lambda p, a: {},
            prediction_repository=pred_repo,
            model_repository=model_repo,
            leaderboard_repository=lb_repo,
        )

        def boom():
            service.stop_event.set()
            raise RuntimeError("boom")

        service.run_once = boom

        with self.assertLogs("node_template.services.score_service", level="ERROR"):
            await service.run()

        self.assertEqual(pred_repo.rollback_calls, 1)
        self.assertEqual(model_repo.rollback_calls, 1)
        self.assertEqual(lb_repo.rollback_calls, 1)


if __name__ == "__main__":
    unittest.main()
