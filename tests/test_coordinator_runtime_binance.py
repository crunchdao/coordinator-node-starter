from __future__ import annotations

from datetime import datetime, timezone
from math import log, sqrt
from types import SimpleNamespace
import unittest

from coordinator_runtime.data_sources.binance import (
    fetch_binance_klines,
    provide_binance_raw_input,
    resolve_binance_ground_truth,
)


class TestCoordinatorRuntimeBinance(unittest.TestCase):
    def test_fetch_binance_klines_uses_sdk_client_when_provided(self):
        class StubBinanceClient:
            def __init__(self):
                self.last_kwargs = None

            def get_klines(self, **kwargs):
                self.last_kwargs = kwargs
                return [
                    [
                        1700000000000,
                        "100.0",
                        "101.0",
                        "99.0",
                        "100.5",
                        "123.0",
                    ]
                ]

        client = StubBinanceClient()

        rows = fetch_binance_klines(
            symbol="BTCUSDT",
            interval="1m",
            limit=1,
            client=client,
        )

        self.assertEqual(
            client.last_kwargs,
            {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "limit": 1,
            },
        )
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["close"], 100.5)

    def test_provide_binance_raw_input_shapes_payload(self):
        def fetch_klines(symbol: str, interval: str, limit: int):
            self.assertEqual(symbol, "BTCUSDT")
            self.assertEqual(interval, "1m")
            self.assertEqual(limit, 3)
            return [
                {"ts": 1700000000, "close": 100.0},
                {"ts": 1700000060, "close": 101.0},
                {"ts": 1700000120, "close": 102.0},
            ]

        payload = provide_binance_raw_input(
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
            symbol="BTCUSDT",
            interval="1m",
            window_minutes=3,
            horizon_minutes=5,
            fetch_klines=fetch_klines,
        )

        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(payload["horizon_minutes"], 5)
        self.assertEqual(payload["asof_ts"], 1700000120)
        self.assertEqual(len(payload["candles_1m"]), 3)

    def test_provide_binance_raw_input_falls_back_when_fetch_fails(self):
        def fetch_klines(symbol: str, interval: str, limit: int):
            raise RuntimeError("network unavailable")

        payload = provide_binance_raw_input(
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
            symbol="BTCUSDT",
            interval="1m",
            window_minutes=4,
            horizon_minutes=5,
            fetch_klines=fetch_klines,
        )

        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(len(payload["candles_1m"]), 4)
        self.assertGreater(payload["candles_1m"][-1]["close"], payload["candles_1m"][0]["close"])

    def test_resolve_binance_ground_truth_computes_return_and_volatility(self):
        prediction = SimpleNamespace(
            inference_input={
                "candles_1m": [
                    {"close": 98.0},
                    {"close": 99.0},
                    {"close": 100.0},
                ]
            }
        )

        closes = [100.0, 101.0, 102.0, 101.0, 102.0, 103.0]

        result = resolve_binance_ground_truth(
            prediction,
            symbol="BTCUSDT",
            horizon_minutes=5,
            fetch_recent_closes=lambda _symbol, _count, _interval: closes,
        )

        expected_return = log(103.0 / 100.0)
        one_min_returns = [log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        expected_vol = sqrt(sum(value * value for value in one_min_returns[-5:]))

        self.assertAlmostEqual(result["return_5m"], expected_return, places=12)
        self.assertAlmostEqual(result["volatility_5m"], expected_vol, places=12)


if __name__ == "__main__":
    unittest.main()
