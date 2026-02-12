from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from coordinator_core.entities.market_record import MarketRecord
from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord, PredictionScore
from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from coordinator_core.services.interfaces.prediction_repository import PredictionRepository
from node_template.workers.report_worker import (
    get_feeds,
    get_feeds_tail,
    get_leaderboard,
    get_models,
    get_models_global,
    get_models_params,
    get_predictions,
    get_report_schema,
    get_report_schema_leaderboard_columns,
    get_report_schema_metrics_widgets,
    resolve_report_schema,
)


class InMemoryModelRepository(ModelRepository):
    def __init__(self, models: dict[str, Model]):
        self._models = models

    def fetch_all(self) -> dict[str, Model]:
        return self._models

    def fetch_by_ids(self, ids: list[str]) -> dict[str, Model]:
        return {k: v for k, v in self._models.items() if k in ids}

    def fetch(self, model_id: str) -> Model | None:
        return self._models.get(model_id)

    def save(self, model: Model) -> None:
        self._models[model.id] = model

    def save_all(self, models):
        for model in models:
            self.save(model)


class InMemoryLeaderboardRepository(LeaderboardRepository):
    def __init__(self, latest: dict | None):
        self._latest = latest

    def save(self, leaderboard_entries, meta=None) -> None:
        self._latest = {
            "id": "lbr",
            "created_at": datetime.now(timezone.utc),
            "entries": leaderboard_entries,
            "meta": meta or {},
        }

    def get_latest(self) -> dict | None:
        return self._latest


class InMemoryPredictionRepository(PredictionRepository):
    def __init__(self, predictions: list[PredictionRecord]):
        self._predictions = predictions

    def save(self, prediction: PredictionRecord) -> None:
        raise NotImplementedError

    def save_all(self, predictions):
        raise NotImplementedError

    def fetch_ready_to_score(self):
        return []

    def query_scores(self, model_ids: list[str], _from: datetime | None, to: datetime | None):
        result: dict[str, list[PredictionRecord]] = {}
        for prediction in self._predictions:
            if model_ids and prediction.model_id not in model_ids:
                continue
            if _from and prediction.performed_at < _from:
                continue
            if to and prediction.performed_at > to:
                continue
            result.setdefault(prediction.model_id, []).append(prediction)
        return result


class InMemoryMarketRecordRepository:
    def __init__(self, records: list[MarketRecord], summaries: list[dict] | None = None):
        self._records = records
        self._summaries = summaries or []

    def list_indexed_feeds(self):
        return list(self._summaries)

    def tail_records(self, *, provider=None, asset=None, kind=None, granularity=None, limit=20):
        rows = list(self._records)
        if provider is not None:
            rows = [row for row in rows if row.provider == provider]
        if asset is not None:
            rows = [row for row in rows if row.asset == asset]
        if kind is not None:
            rows = [row for row in rows if row.kind == kind]
        if granularity is not None:
            rows = [row for row in rows if row.granularity == granularity]

        rows.sort(key=lambda item: item.ts_event, reverse=True)
        return rows[:limit]


class TestNodeTemplateReportWorker(unittest.TestCase):
    def _make_prediction(self, model_id: str, scope_key: str, scope: dict, score_value: float):
        now = datetime.now(timezone.utc)
        prediction = PredictionRecord(
            id=f"pre-{model_id}-{scope_key}",
            model_id=model_id,
            prediction_config_id="CFG_1",
            scope_key=scope_key,
            scope=scope,
            status="SUCCESS",
            exec_time_ms=1.0,
            inference_input={},
            inference_output={},
            performed_at=now - timedelta(minutes=2),
            resolvable_at=now - timedelta(minutes=1),
        )
        prediction.score = PredictionScore(
            value=score_value,
            success=True,
            failed_reason=None,
            scored_at=now - timedelta(seconds=30),
        )
        return prediction

    def test_get_models_returns_expected_shape(self):
        models = {
            "m1": Model(
                id="m1",
                name="model-alpha",
                player_id="p1",
                player_name="alice",
                deployment_identifier="d1",
            )
        }
        repo = InMemoryModelRepository(models)

        response = get_models(repo)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["model_id"], "m1")
        self.assertEqual(response[0]["model_name"], "model-alpha")
        self.assertEqual(response[0]["cruncher_name"], "alice")

    def test_get_leaderboard_sorts_by_rank(self):
        latest = {
            "id": "l1",
            "created_at": datetime(2026, 2, 10, tzinfo=timezone.utc),
            "entries": [
                {
                    "rank": 2,
                    "model_id": "m2",
                    "score": {
                        "metrics": {"wealth": 200.0},
                        "ranking": {"key": "wealth", "direction": "desc"},
                        "payload": {},
                    },
                    "model_name": "two",
                    "cruncher_name": "bob",
                },
                {
                    "rank": 1,
                    "model_id": "m1",
                    "score": {
                        "metrics": {"wealth": 300.0},
                        "ranking": {"key": "wealth", "direction": "desc"},
                        "payload": {},
                    },
                    "model_name": "one",
                    "cruncher_name": "alice",
                },
            ],
            "meta": {},
        }
        repo = InMemoryLeaderboardRepository(latest)

        response = get_leaderboard(repo)
        self.assertEqual([entry["rank"] for entry in response], [1, 2])
        self.assertEqual(response[0]["model_id"], "m1")
        self.assertEqual(response[0]["score_metrics"]["wealth"], 300.0)
        self.assertEqual(response[0]["score_ranking"]["key"], "wealth")
        self.assertEqual(response[0]["score_wealth"], 300.0)

    def test_get_leaderboard_returns_empty_when_missing(self):
        repo = InMemoryLeaderboardRepository(None)
        self.assertEqual(get_leaderboard(repo), [])

    def test_get_models_global_returns_entries(self):
        predictions = [
            self._make_prediction("m1", "BTC-60", {"asset": "BTC", "horizon": 60}, 0.4),
            self._make_prediction("m1", "ETH-60", {"asset": "ETH", "horizon": 60}, 0.6),
        ]
        repo = InMemoryPredictionRepository(predictions)

        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc)

        response = get_models_global(["m1"], start, end, repo)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["model_id"], "m1")
        self.assertIn("anchor", response[0]["score_metrics"])
        self.assertEqual(response[0]["score_ranking"]["key"], "anchor")
        self.assertIn("score_anchor", response[0])

    def test_get_models_params_returns_grouped_entries(self):
        predictions = [
            self._make_prediction("m1", "BTC-60", {"asset": "BTC", "horizon": 60}, 0.4),
            self._make_prediction("m1", "BTC-60", {"asset": "BTC", "horizon": 60}, 0.6),
            self._make_prediction("m1", "ETH-60", {"asset": "ETH", "horizon": 60}, 0.9),
        ]
        repo = InMemoryPredictionRepository(predictions)

        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc)

        response = get_models_params(["m1"], start, end, repo)
        self.assertEqual(len(response), 2)
        btc = next(item for item in response if item["scope_key"] == "BTC-60")
        self.assertIn("anchor", btc["score_metrics"])
        self.assertEqual(btc["score_ranking"]["key"], "anchor")
        self.assertIn("score_anchor", btc)

    def test_get_predictions_requires_single_model(self):
        repo = InMemoryPredictionRepository([])
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc)

        with self.assertRaises(HTTPException):
            get_predictions(["m1", "m2"], start, end, repo)

    def test_get_predictions_returns_scored_rows(self):
        predictions = [self._make_prediction("m1", "BTC-60", {"asset": "BTC", "horizon": 60}, 0.4)]
        repo = InMemoryPredictionRepository(predictions)
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc)

        response = get_predictions(["m1"], start, end, repo)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["model_id"], "m1")
        self.assertEqual(response[0]["scope_key"], "BTC-60")
        self.assertEqual(response[0]["score_value"], 0.4)

    def test_get_feeds_returns_indexed_feed_summaries(self):
        summaries = [
            {
                "provider": "pyth",
                "asset": "BTC",
                "kind": "tick",
                "granularity": "1s",
                "record_count": 123,
                "oldest_ts": "2026-01-01T00:00:00+00:00",
                "newest_ts": "2026-01-02T00:00:00+00:00",
                "watermark_ts": "2026-01-02T00:00:00+00:00",
                "watermark_updated_at": "2026-01-02T00:00:01+00:00",
            }
        ]
        repo = InMemoryMarketRecordRepository(records=[], summaries=summaries)

        response = get_feeds(repo)
        self.assertEqual(response, summaries)

    def test_get_feeds_tail_returns_recent_samples(self):
        base = datetime.now(timezone.utc)
        records = [
            MarketRecord(
                provider="pyth",
                asset="BTC",
                kind="tick",
                granularity="1s",
                ts_event=base - timedelta(seconds=idx),
                values={"price": 50_000.0 + idx},
                meta={"sample": idx},
            )
            for idx in range(30)
        ]
        repo = InMemoryMarketRecordRepository(records=records)

        response = get_feeds_tail(provider="pyth", asset="BTC", kind="tick", granularity="1s", limit=20, market_repo=repo)

        self.assertEqual(len(response), 20)
        self.assertEqual(response[0]["provider"], "pyth")
        self.assertEqual(response[0]["asset"], "BTC")
        self.assertIn("values", response[0])
        self.assertIn("meta", response[0])

    def test_report_schema_endpoints_return_expected_shape(self):
        schema = get_report_schema()
        self.assertIn("schema_version", schema)
        self.assertIn("leaderboard_columns", schema)
        self.assertIn("metrics_widgets", schema)
        self.assertIsInstance(get_report_schema_leaderboard_columns(), list)
        self.assertIsInstance(get_report_schema_metrics_widgets(), list)

    def test_resolve_report_schema_for_risk_profile(self):
        schema = resolve_report_schema(
            "node_template.extensions.risk_adjusted_callables:risk_adjusted_report_schema"
        )
        leaderboard_props = {
            col.get("property")
            for col in schema["leaderboard_columns"]
            if isinstance(col, dict)
        }
        self.assertIn("score_sharpe_like", leaderboard_props)
        self.assertIn("score_wealth", leaderboard_props)


if __name__ == "__main__":
    unittest.main()
