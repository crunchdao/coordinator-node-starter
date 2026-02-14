from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator_node.entities.feed_record import FeedRecord
from coordinator_node.entities.model import Model
from coordinator_node.entities.prediction import InputRecord, PredictionRecord, ScoreRecord
from coordinator_node.crunch_config import Aggregation, AggregationWindow, CrunchConfig
from coordinator_node.services.score import ScoreService


class MemInputRepository:
    def __init__(self, records: list[InputRecord] | None = None) -> None:
        self._records = list(records or [])

    def save(self, record: InputRecord) -> None:
        for i, r in enumerate(self._records):
            if r.id == record.id:
                self._records[i] = record
                return
        self._records.append(record)

    def find(self, *, status: str | None = None, resolvable_before: datetime | None = None,
             **kwargs: Any) -> list[InputRecord]:
        results = list(self._records)
        if status is not None:
            results = [r for r in results if r.status == status]
        if resolvable_before is not None:
            results = [r for r in results if r.resolvable_at and r.resolvable_at <= resolvable_before]
        return results


class MemPredictionRepository:
    def __init__(self, predictions: list[PredictionRecord] | None = None) -> None:
        self._predictions = list(predictions or [])

    def find(self, *, status: str | None = None, **kwargs: Any) -> list[PredictionRecord]:
        results = list(self._predictions)
        if status is not None:
            results = [p for p in results if p.status == status]
        return results

    def save(self, prediction: PredictionRecord) -> None:
        for i, p in enumerate(self._predictions):
            if p.id == prediction.id:
                self._predictions[i] = prediction
                return
        self._predictions.append(prediction)

    def save_all(self, predictions: Any) -> None:
        for p in predictions:
            self.save(p)


class MemScoreRepository:
    def __init__(self) -> None:
        self.scores: list[ScoreRecord] = []

    def save(self, record: ScoreRecord) -> None:
        for i, s in enumerate(self.scores):
            if s.id == record.id:
                self.scores[i] = record
                return
        self.scores.append(record)

    def find(self, **kwargs: Any) -> list[ScoreRecord]:
        return list(self.scores)


class MemModelRepository:
    def __init__(self) -> None:
        self.models = {"m1": Model(id="m1", name="model-one", player_id="p1",
                                   player_name="alice", deployment_identifier="d1")}

    def fetch_all(self) -> dict[str, Model]:
        return self.models


class MemSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: list = []

    def save(self, record) -> None:
        self.snapshots.append(record)

    def find(self, *, model_id=None, since=None, until=None, limit=None) -> list:
        results = list(self.snapshots)
        if model_id is not None:
            results = [s for s in results if s.model_id == model_id]
        return results


class MemLeaderboardRepository:
    def __init__(self) -> None:
        self.latest: Any = None

    def save(self, entries: Any, meta: Any = None) -> None:
        self.latest = {"entries": entries, "meta": meta or {}}

    def get_latest(self) -> Any:
        return self.latest


class FakeFeedReader:
    def __init__(self, records: list | None = None) -> None:
        self._records = records or []

    def fetch_window(self, start=None, end=None, source=None, subject=None,
                     kind=None, granularity=None) -> list:
        return self._records


now = datetime.now(timezone.utc)


def _make_input(status: str = "RECEIVED") -> InputRecord:
    return InputRecord(
        id="inp-1", raw_data={"symbol": "BTC"},
        scope={"source": "pyth", "subject": "BTC", "kind": "tick", "granularity": "1s"},
        status=status, received_at=now - timedelta(minutes=5),
        resolvable_at=now - timedelta(minutes=1),
    )


def _make_prediction(input_id: str = "inp-1", status: str = "PENDING") -> PredictionRecord:
    return PredictionRecord(
        id="pre-1", input_id=input_id, model_id="m1",
        prediction_config_id="CFG_1",
        scope_key="BTC-60", scope={"subject": "BTC", "horizon": 60},
        status=status, exec_time_ms=10.0,
        inference_output={"value": 0.5},
        performed_at=now - timedelta(minutes=5),
        resolvable_at=now - timedelta(minutes=1),
    )


def _make_feed_records(entry_price: float = 100.0, resolved_price: float = 105.0) -> list[FeedRecord]:
    return [
        FeedRecord(source="pyth", subject="BTC", kind="tick", granularity="1s",
                   ts_event=now - timedelta(minutes=5), values={"close": entry_price}),
        FeedRecord(source="pyth", subject="BTC", kind="tick", granularity="1s",
                   ts_event=now - timedelta(minutes=1), values={"close": resolved_price}),
    ]


def _build_service(*, inputs=None, predictions=None, feed_records=None, contract=None):
    return ScoreService(
        checkpoint_interval_seconds=60,
        scoring_function=lambda pred, act: {"value": 0.5, "success": True, "failed_reason": None},
        feed_reader=FakeFeedReader(records=feed_records or []),
        input_repository=MemInputRepository(inputs or []),
        prediction_repository=MemPredictionRepository(predictions or []),
        score_repository=MemScoreRepository(),
        snapshot_repository=MemSnapshotRepository(),
        model_repository=MemModelRepository(),
        leaderboard_repository=MemLeaderboardRepository(),
        contract=contract,
    )


class TestScoreService(unittest.TestCase):
    def test_resolve_inputs_then_score(self):
        service = _build_service(
            inputs=[_make_input()],
            predictions=[_make_prediction()],
            feed_records=_make_feed_records(),
        )

        changed = service.run_once()

        self.assertTrue(changed)
        self.assertEqual(len(service.score_repository.scores), 1)
        self.assertEqual(service.score_repository.scores[0].result["value"], 0.5)

    def test_no_actuals_means_no_scoring(self):
        service = _build_service(
            inputs=[_make_input()],
            predictions=[_make_prediction()],
            feed_records=[],
        )

        with self.assertLogs("coordinator_node.services.score", level="INFO"):
            changed = service.run_once()

        self.assertFalse(changed)
        self.assertEqual(len(service.score_repository.scores), 0)

    def test_no_predictions_means_no_scoring(self):
        service = _build_service()

        with self.assertLogs("coordinator_node.services.score", level="INFO"):
            changed = service.run_once()

        self.assertFalse(changed)

    def test_idempotent(self):
        service = _build_service(
            inputs=[_make_input()],
            predictions=[_make_prediction()],
            feed_records=_make_feed_records(),
        )

        service.run_once()
        self.assertEqual(len(service.score_repository.scores), 1)

        with self.assertLogs("coordinator_node.services.score", level="INFO"):
            changed = service.run_once()
        self.assertFalse(changed)
        self.assertEqual(len(service.score_repository.scores), 1)

    def test_rank_ascending(self):
        contract = CrunchConfig(
            aggregation=Aggregation(
                windows={"loss": AggregationWindow(hours=24)},
                ranking_key="loss", ranking_direction="asc",
            )
        )
        service = _build_service(contract=contract)

        ranked = service._rank_leaderboard([
            {"model_id": "m1", "score": {"metrics": {"loss": 0.4}, "ranking": {}, "payload": {}}},
            {"model_id": "m2", "score": {"metrics": {"loss": 0.2}, "ranking": {}, "payload": {}}},
        ])
        self.assertEqual([e["model_id"] for e in ranked], ["m2", "m1"])
        self.assertEqual([e["rank"] for e in ranked], [1, 2])


class TestScoreServiceRunLoop(unittest.IsolatedAsyncioTestCase):
    async def test_rollback_on_exception(self):
        service = _build_service()

        def boom():
            service.stop_event.set()
            raise RuntimeError("boom")

        service.run_once = boom

        with self.assertLogs("coordinator_node.services.score", level="ERROR"):
            await service.run()


if __name__ == "__main__":
    unittest.main()
