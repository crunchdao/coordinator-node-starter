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


class TestPythUpdownBtcPlugin(unittest.TestCase):
    def test_validate_probability_output_accepts_valid_payload(self):
        result = validate_probability_up_output({"p_up": 0.75})
        self.assertEqual(result, {"p_up": 0.75})

    def test_validate_probability_output_rejects_invalid_payload(self):
        with self.assertRaises(ValueError):
            validate_probability_up_output({"foo": 1})

    def test_score_brier_probability(self):
        result = score_brier_probability_up({"p_up": 0.8}, {"y_up": True})
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["value"], 0.96, places=6)

    def test_build_raw_input_from_pyth(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        payload = build_raw_input_from_pyth(now=now, client=_FakePythClient(price=42000.0))

        self.assertEqual(payload["asset"], "BTC")
        self.assertEqual(payload["price"], 42000.0)
        self.assertEqual(payload["as_of"], now.isoformat())

    def test_resolve_ground_truth_returns_none_for_non_btc(self):
        prediction = PredictionRecord(
            id="p1",
            model_id="m1",
            asset="ETH",
            horizon=60,
            step=60,
            status="SUCCESS",
            exec_time_ms=1.0,
            inference_input={"price": 100.0},
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
            asset="BTC",
            horizon=60,
            step=60,
            status="SUCCESS",
            exec_time_ms=1.0,
            inference_input={"price": 100.0},
            inference_output={"p_up": 0.5},
            performed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            resolvable_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )

        truth = resolve_ground_truth_from_pyth(prediction=prediction, client=_FakePythClient(price=101.0))
        self.assertIsNotNone(truth)
        self.assertTrue(truth["y_up"])


if __name__ == "__main__":
    unittest.main()
