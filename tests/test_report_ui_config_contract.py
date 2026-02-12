from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from coordinator_core.entities.prediction import PredictionRecord, PredictionScore
from coordinator_core.schemas import LeaderboardEntryEnvelope
from node_template.contracts import CrunchContract
from node_template.workers.report_worker import (
    auto_report_schema,
    get_leaderboard,
    get_models_global,
    get_models_params,
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
        self.contract = CrunchContract()
        self.backend_schema = auto_report_schema(self.contract)

    def test_leaderboard_columns_include_all_aggregation_windows(self):
        column_props = {
            col["property"]
            for col in self.backend_schema["leaderboard_columns"]
            if col.get("type") == "VALUE"
        }
        for window_name in self.contract.aggregation.windows:
            self.assertIn(window_name, column_props)

    def test_leaderboard_columns_match_leaderboard_payload(self):
        entry = LeaderboardEntryEnvelope(
            model_id="m1",
            rank=1,
            model_name="model-one",
            cruncher_name="alice",
            score={
                "metrics": {
                    "score_recent": 0.4,
                    "score_steady": 0.5,
                    "score_anchor": 0.6,
                },
                "ranking": {
                    "key": "score_recent",
                    "value": 0.4,
                    "direction": "desc",
                },
                "payload": {},
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

        for window_name in self.contract.aggregation.windows:
            self.assertIn(f"score_{window_name}", payload_row)

    def test_widget_series_match_aggregation_windows(self):
        widgets = self.backend_schema["metrics_widgets"]
        score_metrics_widget = next(w for w in widgets if w["endpointUrl"] == "/reports/models/global")
        series_names = {
            s["name"]
            for s in score_metrics_widget["nativeConfiguration"]["yAxis"]["series"]
        }
        for window_name in self.contract.aggregation.windows:
            self.assertIn(window_name, series_names)

    def test_models_global_uses_contract_ranking(self):
        now = datetime.now(timezone.utc)
        predictions = []
        for idx, value in enumerate([0.02, -0.01, 0.03], start=1):
            prediction = PredictionRecord(
                id=f"p-{idx}",
                model_id="m1",
                prediction_config_id="CFG_001",
                scope_key="BTC-60",
                scope={"asset": "BTC", "horizon": 60},
                status="SUCCESS",
                exec_time_ms=1.0,
                inference_input={},
                inference_output={},
                performed_at=now - timedelta(minutes=5 - idx),
                resolvable_at=now - timedelta(minutes=4 - idx),
            )
            prediction.score = PredictionScore(value=value, success=True, failed_reason=None)
            predictions.append(prediction)

        repo = _InMemoryPredictionRepository(predictions)
        response = get_models_global(["m1"], now - timedelta(hours=1), now, repo)

        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["score_ranking"]["key"], self.contract.aggregation.ranking_key)
        self.assertEqual(response[0]["score_ranking"]["direction"], self.contract.aggregation.ranking_direction)


if __name__ == "__main__":
    unittest.main()
