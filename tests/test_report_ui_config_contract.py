from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord, PredictionScore
from coordinator_core.schemas import LeaderboardEntryEnvelope
from node_template.workers.report_worker import (
    get_leaderboard,
    get_models_global,
    get_models_params,
    resolve_report_schema,
)


class _InMemoryLeaderboardRepository:
    def __init__(self, latest: dict | None):
        self._latest = latest

    def save(self, leaderboard_entries, meta=None):
        raise NotImplementedError

    def get_latest(self):
        return self._latest


class _InMemoryPredictionRepository:
    def __init__(self, predictions: list[PredictionRecord]):
        self._predictions = predictions

    def save(self, prediction):
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


class TestReportUiConfigContract(unittest.TestCase):
    def setUp(self):
        self.leaderboard_config = json.loads(Path("deployment/report-ui/config/leaderboard-columns.json").read_text())
        self.widgets_config = json.loads(Path("deployment/report-ui/config/metrics-widgets.json").read_text())
        self.backend_schema = resolve_report_schema(
            "node_template.extensions.risk_adjusted_callables:risk_adjusted_report_schema"
        )

    def test_leaderboard_columns_match_leaderboard_payload(self):
        entry = LeaderboardEntryEnvelope(
            model_id="m1",
            rank=1,
            model_name="model-one",
            cruncher_name="alice",
            score={
                "metrics": {
                    "sharpe_like": 1.5,
                    "wealth": 1.12,
                    "mean_return": 0.02,
                    "volatility": 0.01,
                    "hit_rate": 0.65,
                },
                "ranking": {
                    "key": "sharpe_like",
                    "value": 1.5,
                    "direction": "desc",
                    "tie_breakers": ["wealth", "mean_return"],
                },
                "payload": {"num_predictions": 42},
            },
        )
        leaderboard_repo = _InMemoryLeaderboardRepository(
            {
                "id": "l1",
                "created_at": datetime.now(timezone.utc),
                "entries": [entry.model_dump()],
                "meta": {},
            }
        )

        response = get_leaderboard(leaderboard_repo)
        self.assertEqual(len(response), 1)
        payload_row = response[0]

        configured_properties = [c["property"] for c in self.leaderboard_config if c.get("type") == "VALUE"]
        backend_properties = {
            c.get("property")
            for c in self.backend_schema.get("leaderboard_columns", [])
            if isinstance(c, dict)
        }
        for prop in configured_properties:
            self.assertIn(prop, backend_properties, f"Override leaderboard property '{prop}' not present in backend schema")
            self.assertIn(prop, payload_row, f"Leaderboard column property '{prop}' missing from payload")

    def test_widget_series_match_report_endpoints(self):
        now = datetime.now(timezone.utc)
        predictions = []
        for idx, value in enumerate([0.02, -0.01, 0.03], start=1):
            prediction = PredictionRecord(
                id=f"p-{idx}",
                model_id="m1",
                prediction_config_id="CFG_001",
                scope_key="BTC-60",
                scope={"asset": "BTC", "horizon": 60, "step": 60},
                status="SUCCESS",
                exec_time_ms=1.0,
                inference_input={},
                inference_output={},
                performed_at=now - timedelta(minutes=5 - idx),
                resolvable_at=now - timedelta(minutes=4 - idx),
            )
            prediction.score = PredictionScore(value=value, success=True, failed_reason=None)
            predictions.append(prediction)

        prediction_repo = _InMemoryPredictionRepository(predictions)
        start = now - timedelta(hours=1)
        end = now

        endpoint_payloads = {
            "/reports/models/global": get_models_global(["m1"], start, end, prediction_repo),
            "/reports/models/params": get_models_params(["m1"], start, end, prediction_repo),
        }

        backend_series_by_endpoint: dict[str, set[str]] = {}
        for widget in self.backend_schema.get("metrics_widgets", []):
            if not isinstance(widget, dict):
                continue
            endpoint = widget.get("endpointUrl")
            series = widget.get("nativeConfiguration", {}).get("yAxis", {}).get("series", [])
            if not isinstance(endpoint, str):
                continue
            backend_series_by_endpoint.setdefault(endpoint, set())
            for s in series:
                if isinstance(s, dict) and isinstance(s.get("name"), str):
                    backend_series_by_endpoint[endpoint].add(s["name"])

        for widget in self.widgets_config:
            endpoint = widget.get("endpointUrl")
            if endpoint not in endpoint_payloads:
                continue

            rows = endpoint_payloads[endpoint]
            self.assertTrue(rows, f"No rows returned for endpoint {endpoint}")
            row = rows[0]
            series = widget.get("nativeConfiguration", {}).get("yAxis", {}).get("series", [])
            for s in series:
                name = s.get("name")
                self.assertIn(name, backend_series_by_endpoint.get(endpoint, set()))
                self.assertIn(name, row, f"Widget series '{name}' missing from endpoint payload {endpoint}")


if __name__ == "__main__":
    unittest.main()
