from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from coordinator_core.entities.prediction import PredictionRecord
from node_template.plugins.pyth_updown_btc import (
    build_raw_input_from_pyth,
    resolve_ground_truth_from_pyth,
    score_brier_probability_up,
    validate_probability_up_output,
)


class _FakePythClient:
    def __init__(self, price: float = 100.0, confidence: float = 0.1, publish_time: int = 1735689600):
        self._price = price
        self._confidence = confidence
        self._publish_time = publish_time

    def get_latest_price(self, feed_id: str):
        return {
            "price": self._price,
            "confidence": self._confidence,
            "publish_time": self._publish_time,
            "feed_id": feed_id,
        }


class _MissingPythClient:
    def get_latest_price(self, feed_id: str):
        return None


class TestPythUpdownBtcPlugin(unittest.TestCase):
    def test_validate_probability_output_accepts_valid_payload(self):
        result = validate_probability_up_output({"p_up": 0.75})
        self.assertEqual(result, {"p_up": 0.75})

    def test_validate_probability_output_accepts_density_payload(self):
        payload = {
            "result": [
                {
                    "type": "mixture",
                    "components": [
                        {
                            "weight": 1.0,
                            "density": {
                                "type": "builtin",
                                "name": "norm",
                                "params": {"loc": 0.0, "scale": 1.0},
                            },
                        }
                    ],
                }
            ]
        }

        result = validate_probability_up_output(payload)
        self.assertIn("p_up", result)
        self.assertAlmostEqual(result["p_up"], 0.5, places=6)

    def test_validate_probability_output_rejects_invalid_payload(self):
        with self.assertRaises(ValueError):
            validate_probability_up_output({"foo": 1})

    def test_score_brier_probability_from_p_up(self):
        result = score_brier_probability_up({"p_up": 0.8}, {"y_up": True})
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["value"], 0.96, places=6)

    def test_score_brier_probability_from_density_payload(self):
        payload = {
            "result": [
                {
                    "type": "mixture",
                    "components": [
                        {
                            "weight": 1.0,
                            "density": {
                                "type": "builtin",
                                "name": "norm",
                                "params": {"loc": 1.0, "scale": 0.5},
                            },
                        }
                    ],
                }
            ]
        }
        result = score_brier_probability_up(payload, {"y_up": True})
        self.assertTrue(result["success"])
        self.assertGreater(result["value"], 0.8)

    def test_build_raw_input_from_pyth_returns_price_data(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        payload = build_raw_input_from_pyth(now=now, client=_FakePythClient(price=42000.0, confidence=20.0))

        self.assertIn("BTC", payload)
        self.assertEqual(len(payload["BTC"]), 3)
        self.assertEqual(payload["BTC"][-1][1], 42000.0)

    def test_build_raw_input_uses_fallback_when_pyth_unavailable(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        payload = build_raw_input_from_pyth(now=now, client=_MissingPythClient())

        self.assertIn("BTC", payload)
        self.assertEqual(len(payload["BTC"]), 3)

    def test_resolve_ground_truth_returns_none_for_non_btc_scope(self):
        prediction = PredictionRecord(
            id="p1",
            model_id="m1",
            prediction_config_id="CFG_1",
            scope_key="ETH-60",
            scope={"asset": "ETH", "horizon": 60, "step": 60},
            status="SUCCESS",
            exec_time_ms=1.0,
            inference_input={"ETH": [(1, 100.0)]},
            inference_output={"p_up": 0.5},
            performed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            resolvable_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        truth = resolve_ground_truth_from_pyth(prediction=prediction, client=_FakePythClient(price=101.0))
        self.assertIsNone(truth)

    def test_resolve_ground_truth_compares_latest_with_entry(self):
        prediction = PredictionRecord(
            id="p1",
            model_id="m1",
            prediction_config_id="CFG_1",
            scope_key="BTC-60",
            scope={"asset": "BTC", "horizon": 60, "step": 60},
            status="SUCCESS",
            exec_time_ms=1.0,
            inference_input={"BTC": [(100, 100.0), (160, 100.5)]},
            inference_output={"p_up": 0.5},
            performed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            resolvable_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        truth = resolve_ground_truth_from_pyth(prediction=prediction, client=_FakePythClient(price=101.0))
        self.assertIsNotNone(truth)
        self.assertTrue(truth["y_up"])

    def test_resolve_ground_truth_uses_fallback_when_pyth_unavailable(self):
        prediction = PredictionRecord(
            id="p1",
            model_id="m1",
            prediction_config_id="CFG_1",
            scope_key="BTC-60",
            scope={"asset": "BTC", "horizon": 60, "step": 60},
            status="SUCCESS",
            exec_time_ms=1.0,
            inference_input={"BTC": [(100, 100.0), (160, 100.5)]},
            inference_output={"p_up": 0.5},
            performed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            resolvable_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        truth = resolve_ground_truth_from_pyth(prediction=prediction, client=_MissingPythClient())
        self.assertIsNotNone(truth)
        self.assertIn("y_up", truth)


if __name__ == "__main__":
    unittest.main()
