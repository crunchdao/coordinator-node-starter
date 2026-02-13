from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from coordinator.entities.market_record import MarketRecord
from coordinator.entities.model import Model
from coordinator.contracts import CrunchContract
from coordinator.workers.report_worker import (
    auto_report_schema,
    get_feeds,
    get_feeds_tail,
    get_leaderboard,
    get_models,
    get_report_schema,
    get_report_schema_leaderboard_columns,
    get_report_schema_metrics_widgets,
)


class InMemoryModelRepository:
    def __init__(self, models: dict[str, Model]):
        self._models = models

    def fetch_all(self):
        return dict(self._models)

    def save(self, model):
        self._models[model.id] = model

    def save_all(self, models):
        for m in models:
            self.save(m)


class InMemoryLeaderboardRepository:
    def __init__(self, entries=None, meta=None):
        self._latest = {"entries": entries or [], "meta": meta or {}} if entries else None

    def save(self, entries, meta=None):
        self._latest = {"entries": entries, "meta": meta or {}}

    def get_latest(self):
        return self._latest


class InMemoryMarketRecordRepository:
    def __init__(self, records: list[MarketRecord], summaries: list[dict] | None = None):
        self._records = records
        self._summaries = summaries or []

    def list_indexed_feeds(self):
        return list(self._summaries)

    def tail_records(self, *, provider=None, asset=None, kind=None, granularity=None, limit=20):
        rows = list(self._records)
        if provider:
            rows = [r for r in rows if r.provider == provider]
        if asset:
            rows = [r for r in rows if r.asset == asset]
        rows.sort(key=lambda r: r.ts_event, reverse=True)
        return rows[:limit]


class TestNodeTemplateReportWorker(unittest.TestCase):
    def test_get_models_returns_expected_shape(self):
        models = {
            "m1": Model(id="m1", name="model-alpha", player_id="p1",
                        player_name="alice", deployment_identifier="d1"),
        }
        repo = InMemoryModelRepository(models)
        response = get_models(repo)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["model_id"], "m1")
        self.assertEqual(response[0]["model_name"], "model-alpha")

    def test_get_leaderboard_sorts_by_rank(self):
        entries = [
            {"model_id": "m1", "rank": 1, "score": {"metrics": {"score_recent": 0.8},
             "ranking": {"key": "score_recent", "value": 0.8, "direction": "desc"}, "payload": {}}},
            {"model_id": "m2", "rank": 2, "score": {"metrics": {"score_recent": 0.5},
             "ranking": {"key": "score_recent", "value": 0.5, "direction": "desc"}, "payload": {}}},
        ]
        repo = InMemoryLeaderboardRepository(entries=entries)
        response = get_leaderboard(repo)
        self.assertEqual(len(response), 2)
        self.assertEqual(response[0]["rank"], 1)

    def test_get_leaderboard_returns_empty_when_missing(self):
        repo = InMemoryLeaderboardRepository()
        response = get_leaderboard(repo)
        self.assertEqual(response, [])

    def test_get_feeds_returns_indexed_feed_summaries(self):
        summaries = [
            {"provider": "binance", "asset": "BTC", "kind": "candle", "granularity": "1m",
             "record_count": 100, "first_event": "2025-01-01T00:00:00Z",
             "last_event": "2025-01-02T00:00:00Z"},
        ]
        repo = InMemoryMarketRecordRepository(records=[], summaries=summaries)
        response = get_feeds(repo)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["provider"], "binance")

    def test_get_feeds_tail_returns_recent_samples(self):
        now = datetime.now(timezone.utc)
        records = [
            MarketRecord(provider="binance", asset="BTC", kind="candle", granularity="1m",
                         ts_event=now - timedelta(minutes=i), values={"close": 100.0 + i})
            for i in range(5)
        ]
        repo = InMemoryMarketRecordRepository(records=records)
        response = get_feeds_tail(repo, "binance", "BTC", "candle", "1m", 3)
        self.assertEqual(len(response), 3)
        self.assertIn("close", response[0]["values"])

    def test_report_schema_endpoints_return_expected_shape(self):
        schema = get_report_schema()
        self.assertIn("leaderboard_columns", schema)
        self.assertIn("metrics_widgets", schema)

        columns = get_report_schema_leaderboard_columns()
        self.assertIsInstance(columns, list)

        widgets = get_report_schema_metrics_widgets()
        self.assertIsInstance(widgets, list)

    def test_auto_report_schema_generates_from_contract(self):
        contract = CrunchContract()
        schema = auto_report_schema(contract)
        columns = schema.get("leaderboard_columns", [])
        self.assertTrue(len(columns) > 0, "Should generate leaderboard columns from contract")
        props = [c["property"] for c in columns]
        self.assertIn("score_recent", props)


if __name__ == "__main__":
    unittest.main()
