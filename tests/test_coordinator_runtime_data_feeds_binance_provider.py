from __future__ import annotations

import unittest

from coordinator_runtime.data_feeds.providers.binance import BinanceRestClient


class _StubSDKClient:
    def __init__(self):
        self.klines_kwargs = None
        self.symbol = None

    def get_exchange_info(self):
        return {"symbols": [{"symbol": "BTCUSDT"}]}

    def get_klines(self, **kwargs):
        self.klines_kwargs = kwargs
        return [[1700000000000, "1", "2", "0.5", "1.5", "10"]]

    def get_symbol_ticker(self, **kwargs):
        self.symbol = kwargs.get("symbol")
        return {"price": "123.45"}


class TestBinanceRestClient(unittest.TestCase):
    def test_methods_use_python_binance_client_when_injected(self):
        sdk = _StubSDKClient()
        client = BinanceRestClient(sdk_client=sdk)

        exchange_info = client.exchange_info()
        rows = client.klines("BTCUSDT", "1m", limit=3)
        price = client.ticker_price("BTCUSDT")

        self.assertEqual(exchange_info["symbols"][0]["symbol"], "BTCUSDT")
        self.assertEqual(
            sdk.klines_kwargs,
            {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "limit": 3,
            },
        )
        self.assertEqual(rows[0][4], "1.5")
        self.assertEqual(sdk.symbol, "BTCUSDT")
        self.assertEqual(price, 123.45)


if __name__ == "__main__":
    unittest.main()
