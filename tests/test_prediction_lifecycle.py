"""Integration test: full prediction lifecycle with shared in-memory repositories.

input_service → predict_service → [input_repo, prediction_repo] → score_service → [score_repo, leaderboard_repo]

Covers: PENDING → RESOLVED → SCORED, absent model marking, leaderboard rebuild.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import InputRecord, PredictionRecord, ScoreRecord
from node_template.contracts import CrunchContract
from node_template.services.realtime_predict_service import RealtimePredictService
from node_template.services.score_service import ScoreService


# ── shared in-memory repositories ──


class MemInputRepository:
    def __init__(self) -> None:
        self.records: list[InputRecord] = []

    def save(self, record: InputRecord) -> None:
        self.records.append(record)

    def find(self, **kwargs: Any) -> list[InputRecord]:
        return list(self.records)


class MemPredictionRepository:
    def __init__(self) -> None:
        self._predictions: list[PredictionRecord] = []
        self._configs: list[dict[str, Any]] = [
            {
                "id": "CFG_1",
                "scope_key": "BTC-60-60",
                "scope_template": {"asset": "BTC"},
                "schedule": {"prediction_interval_seconds": 60, "resolve_after_seconds": 60},
                "active": True,
                "order": 1,
            },
        ]

    def save(self, prediction: PredictionRecord) -> None:
        for i, p in enumerate(self._predictions):
            if p.id == prediction.id:
                self._predictions[i] = prediction
                return
        self._predictions.append(prediction)

    def save_all(self, predictions: Any) -> None:
        for p in predictions:
            self.save(p)

    def find(self, *, status: str | list[str] | None = None,
             resolvable_before: datetime | None = None, **kwargs: Any) -> list[PredictionRecord]:
        results = list(self._predictions)
        if status is not None:
            statuses = status if isinstance(status, list) else [status]
            results = [p for p in results if p.status in statuses]
        if resolvable_before is not None:
            results = [p for p in results if p.resolvable_at and p.resolvable_at <= resolvable_before]
        return results

    def fetch_active_configs(self) -> list[dict[str, Any]]:
        return self._configs

    @property
    def all(self) -> list[PredictionRecord]:
        return list(self._predictions)


class MemScoreRepository:
    def __init__(self) -> None:
        self.scores: list[ScoreRecord] = []

    def save(self, record: ScoreRecord) -> None:
        for i, s in enumerate(self.scores):
            if s.id == record.id:
                self.scores[i] = record
                return
        self.scores.append(record)

    def find(self, *, prediction_id: str | None = None, **kwargs: Any) -> list[ScoreRecord]:
        results = list(self.scores)
        if prediction_id is not None:
            results = [s for s in results if s.prediction_id == prediction_id]
        return results


class MemModelRepository:
    def __init__(self) -> None:
        self.models: dict[str, Model] = {}

    def save(self, model: Model) -> None:
        self.models[model.id] = model

    def fetch_all(self) -> dict[str, Model]:
        return dict(self.models)


class MemLeaderboardRepository:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def save(self, entries: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> None:
        self.entries = entries

    def get_latest(self) -> list[dict[str, Any]]:
        return self.entries


# ── fakes for external boundaries ──


class FakeModelRun:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.model_name = f"model-{model_id}"
        self.deployment_id = f"dep-{model_id}"
        self.infos = {"cruncher_id": f"p-{model_id}", "cruncher_name": f"Player {model_id}"}


class FakeResult:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.status = "SUCCESS"
        self.exec_time_us = 42


class FakeRunner:
    """Returns deterministic predictions from two models."""
    def __init__(self, outputs: dict[str, dict[str, Any]]) -> None:
        self._outputs = outputs

    async def init(self) -> None:
        pass

    async def sync(self) -> None:
        pass

    async def call(self, method: str, args: Any) -> dict:
        if method == "tick":
            return {FakeModelRun(mid): None for mid in self._outputs}
        return {FakeModelRun(mid): FakeResult(out) for mid, out in self._outputs.items()}


class FakeInputService:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get_input(self, now: datetime) -> dict[str, Any]:
        return dict(self._data)

    def get_ground_truth(self, performed_at: datetime, resolvable_at: datetime,
                         asset: str | None = None) -> dict[str, Any] | None:
        return {"actual_value": 105.0}


# ── lifecycle test ──


class TestPredictionLifecycle(unittest.IsolatedAsyncioTestCase):
    """Full flow: input → predict → score → leaderboard, all in-memory."""

    def setUp(self) -> None:
        self.input_repo = MemInputRepository()
        self.pred_repo = MemPredictionRepository()
        self.score_repo = MemScoreRepository()
        self.model_repo = MemModelRepository()
        self.lb_repo = MemLeaderboardRepository()
        self.contract = CrunchContract()

        self.predict_service = RealtimePredictService(
            checkpoint_interval_seconds=60,
            input_service=FakeInputService({"symbol": "BTC", "asof_ts": 100}),
            contract=self.contract,
            input_repository=self.input_repo,
            model_repository=self.model_repo,
            prediction_repository=self.pred_repo,
            runner=FakeRunner({"m1": {"value": 0.7}, "m2": {"value": 0.3}}),
        )

        self.score_service = ScoreService(
            checkpoint_interval_seconds=60,
            scoring_function=self._score_fn,
            input_service=FakeInputService({"symbol": "BTC", "asof_ts": 100}),
            prediction_repository=self.pred_repo,
            score_repository=self.score_repo,
            model_repository=self.model_repo,
            leaderboard_repository=self.lb_repo,
            contract=self.contract,
        )

    @staticmethod
    def _score_fn(prediction: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
        pred_val = prediction.get("value", 0)
        actual_val = ground_truth.get("actual_value", 0)
        error = abs(pred_val - actual_val)
        return {"value": round(1.0 / (1.0 + error), 4), "success": True, "failed_reason": None}

    async def test_full_lifecycle(self) -> None:
        now = datetime.now(timezone.utc) - timedelta(minutes=5)

        # ── step 1: predict ──
        changed = await self.predict_service.run_once(now=now)
        self.assertTrue(changed)

        # input saved
        self.assertEqual(len(self.input_repo.records), 1)
        inp = self.input_repo.records[0]
        self.assertIn("symbol", inp.raw_data)

        # predictions saved as PENDING
        predictions = self.pred_repo.all
        self.assertEqual(len(predictions), 2)  # m1, m2
        self.assertTrue(all(p.status == "PENDING" for p in predictions))
        self.assertTrue(all(p.input_id == inp.id for p in predictions))

        # models registered
        self.assertIn("m1", self.model_repo.models)
        self.assertIn("m2", self.model_repo.models)

        # ── step 2: score (resolves actuals + scores) ──
        scored = self.score_service.run_once()
        self.assertTrue(scored)

        # predictions now SCORED
        scored_preds = self.pred_repo.find(status="SCORED")
        self.assertEqual(len(scored_preds), 2)

        # score records created
        self.assertEqual(len(self.score_repo.scores), 2)
        for score in self.score_repo.scores:
            self.assertIsNotNone(score.value)
            self.assertTrue(score.success)
            self.assertIn("actual_value", score.actuals)

        # leaderboard rebuilt with both models ranked
        self.assertEqual(len(self.lb_repo.entries), 2)
        ranks = [e["rank"] for e in self.lb_repo.entries]
        self.assertEqual(sorted(ranks), [1, 2])

    async def test_predict_twice_accumulates(self) -> None:
        now = datetime.now(timezone.utc) - timedelta(minutes=5)

        await self.predict_service.run_once(now=now)
        self.assertEqual(len(self.pred_repo.all), 2)

        # second run with different time (past schedule interval)
        later = now + timedelta(minutes=2)
        await self.predict_service.run_once(now=later)
        self.assertEqual(len(self.pred_repo.all), 4)

        # all PENDING
        self.assertTrue(all(p.status == "PENDING" for p in self.pred_repo.all))

    async def test_score_skips_when_no_pending(self) -> None:
        """Score service does nothing when there's nothing to score."""
        with self.assertLogs("node_template.services.score_service", level="INFO"):
            scored = self.score_service.run_once()
        self.assertFalse(scored)
        self.assertEqual(len(self.score_repo.scores), 0)

    async def test_score_idempotent(self) -> None:
        """Running score twice doesn't re-score already scored predictions."""
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        await self.predict_service.run_once(now=now)

        self.score_service.run_once()
        self.assertEqual(len(self.score_repo.scores), 2)

        # second score run — nothing new to score
        with self.assertLogs("node_template.services.score_service", level="INFO"):
            scored = self.score_service.run_once()
        self.assertFalse(scored)
        self.assertEqual(len(self.score_repo.scores), 2)  # unchanged

    async def test_absent_model_marked(self) -> None:
        """If a known model doesn't respond, it gets an ABSENT prediction."""
        # First run registers both models
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        await self.predict_service.run_once(now=now)

        # Swap to a runner that only returns m1
        self.predict_service._runner = FakeRunner({"m1": {"value": 0.5}})

        later = now + timedelta(minutes=2)
        await self.predict_service.run_once(now=later)

        # Should have 4 total: 2 from first run + 2 from second (m1 PENDING + m2 ABSENT)
        all_preds = self.pred_repo.all
        self.assertEqual(len(all_preds), 4)
        absent = [p for p in all_preds if p.status == "ABSENT"]
        self.assertEqual(len(absent), 1)
        self.assertEqual(absent[0].model_id, "m2")

    async def test_input_ids_are_unique(self) -> None:
        now = datetime.now(timezone.utc)
        await self.predict_service.run_once(now=now)
        later = now + timedelta(minutes=2)
        await self.predict_service.run_once(now=later)

        ids = [r.id for r in self.input_repo.records]
        self.assertEqual(len(ids), len(set(ids)), "Input IDs should be unique")

    async def test_leaderboard_ranking_order(self) -> None:
        """Model with higher score should rank first (default desc)."""
        now = datetime.now(timezone.utc) - timedelta(minutes=5)
        await self.predict_service.run_once(now=now)
        self.score_service.run_once()

        # m1 predicted 0.7, m2 predicted 0.3, actual=105.0
        # score = 1/(1+|pred-actual|), so both are tiny but m1 > m2
        entries = self.lb_repo.entries
        self.assertEqual(entries[0]["model_id"], "m1")
        self.assertEqual(entries[0]["rank"], 1)


if __name__ == "__main__":
    unittest.main()
