import unittest

from coordinator_core.entities.model import Model, ModelScore
from coordinator_core.entities.prediction import PredictionRecord, PredictionScore


class TestCoreEntities(unittest.TestCase):
    def test_model_score_supports_windows_rank_key_and_payload(self):
        score = ModelScore(
            windows={"recent": 0.1, "steady": 0.2, "anchor": 0.3},
            rank_key=0.3,
            payload={"crps": 0.55},
        )
        self.assertEqual(score.windows["anchor"], 0.3)
        self.assertEqual(score.rank_key, 0.3)
        self.assertEqual(score.payload["crps"], 0.55)

    def test_model_has_jsonb_extension_payload(self):
        model = Model(
            id="m1",
            name="alpha",
            player_id="p1",
            player_name="alice",
            deployment_identifier="d1",
            meta={"tier": "gold"},
        )
        self.assertEqual(model.meta["tier"], "gold")

    def test_prediction_record_carries_scope_inference_io_and_score(self):
        prediction = PredictionRecord(
            id="pre1",
            model_id="m1",
            prediction_config_id="CFG_001",
            scope_key="BTC-60-60",
            scope={"asset": "BTC", "horizon": 3600, "step": 300},
            status="SUCCESS",
            exec_time_ms=12.5,
            inference_input={"window": [1, 2, 3]},
            inference_output={"distribution": []},
        )

        prediction.score = PredictionScore(value=0.42, success=True, failed_reason=None)

        self.assertEqual(prediction.scope_key, "BTC-60-60")
        self.assertEqual(prediction.scope["asset"], "BTC")
        self.assertIn("window", prediction.inference_input)
        self.assertIn("distribution", prediction.inference_output)
        self.assertEqual(prediction.score.value, 0.42)


if __name__ == "__main__":
    unittest.main()
