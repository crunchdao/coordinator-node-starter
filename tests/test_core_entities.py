import unittest

from coordinator_core.entities.model import Model, ModelScore
from coordinator_core.entities.prediction import InputRecord, PredictionRecord, ScoreRecord


class TestCoreEntities(unittest.TestCase):
    def test_model_score_supports_metrics_ranking_and_payload(self):
        score = ModelScore(
            metrics={"wealth": 1000.0, "hit_rate": 0.7},
            ranking={"key": "wealth", "direction": "desc", "value": 1000.0},
            payload={"crps": 0.55},
        )
        self.assertEqual(score.metrics["wealth"], 1000.0)
        self.assertEqual(score.ranking["key"], "wealth")
        self.assertEqual(score.payload["crps"], 0.55)

    def test_model_has_jsonb_extension_payload(self):
        model = Model(
            id="m1", name="alpha", player_id="p1", player_name="alice",
            deployment_identifier="d1", meta={"tier": "gold"},
        )
        self.assertEqual(model.meta["tier"], "gold")

    def test_input_record(self):
        record = InputRecord(id="inp1", raw_data={"symbol": "BTC", "price": 100.0})
        self.assertEqual(record.raw_data["symbol"], "BTC")
        self.assertEqual(record.status, "RECEIVED")
        self.assertIsNone(record.actuals)

    def test_prediction_record_carries_scope_and_output(self):
        prediction = PredictionRecord(
            id="pre1", input_id="inp1", model_id="m1",
            prediction_config_id="CFG_001",
            scope_key="BTC-60-60",
            scope={"asset": "BTC", "horizon": 3600},
            status="PENDING", exec_time_ms=12.5,
            inference_output={"distribution": []},
        )
        self.assertEqual(prediction.scope_key, "BTC-60-60")
        self.assertEqual(prediction.scope["asset"], "BTC")
        self.assertIn("distribution", prediction.inference_output)

    def test_score_record(self):
        score = ScoreRecord(
            id="scr1", prediction_id="pre1",
            value=0.42, success=True,
        )
        self.assertEqual(score.value, 0.42)
        self.assertTrue(score.success)


if __name__ == "__main__":
    unittest.main()
