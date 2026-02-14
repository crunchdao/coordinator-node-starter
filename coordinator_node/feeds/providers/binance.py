from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

import requests

from coordinator_node.feeds.base import DataFeed, FeedHandle, FeedSink
from coordinator_node.feeds.contracts import (
    SubjectDescriptor,
    FeedFetchRequest,
    FeedSubscription,
    FeedDataRecord,
)
from coordinator_node.feeds.registry import FeedSettings

try:  # pragma: no cover - covered through injection tests
    from binance.client import Client as BinanceSDKClient
except Exception:  # pragma: no cover - keep runtime resilient when dependency is missing
    BinanceSDKClient = None


_BINANCE_API = "https://api.binance.com"


@dataclass
class BinanceRestClient:
    base_url: str = _BINANCE_API
    timeout_seconds: float = 8.0
    sdk_client: Any | None = None

    def __post_init__(self) -> None:
        if self.sdk_client is None:
            self.sdk_client = _build_default_sdk_client(timeout_seconds=self.timeout_seconds)

    def exchange_info(self) -> dict[str, Any]:
        if self.sdk_client is not None:
            payload = self.sdk_client.get_exchange_info()
            return payload if isinstance(payload, dict) else {}

        response = requests.get(
            f"{self.base_url}/api/v3/exchangeInfo",
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int | None = None,
    ) -> list[list[Any]]:
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
        }
        if start_ms is not None:
            params["startTime"] = int(start_ms)
        if end_ms is not None:
            params["endTime"] = int(end_ms)
        if limit is not None:
            params["limit"] = int(limit)

        if self.sdk_client is not None:
            payload = self.sdk_client.get_klines(**params)
            return payload if isinstance(payload, list) else []

        response = requests.get(
            f"{self.base_url}/api/v3/klines",
            params=params,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    def ticker_price(self, symbol: str) -> float:
        if self.sdk_client is not None:
            payload = self.sdk_client.get_symbol_ticker(symbol=symbol)
            if isinstance(payload, dict):
                return float(payload["price"])
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                return float(payload[0]["price"])
            raise ValueError("Unexpected ticker payload from Binance SDK client")

        response = requests.get(
            f"{self.base_url}/api/v3/ticker/price",
            params={"symbol": symbol},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return float(payload["price"])


class _PollingFeedHandle:
    def __init__(self, task: asyncio.Task[None]):
        self._task = task

    async def stop(self) -> None:
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass


import logging as _logging

_logger = _logging.getLogger(__name__)


class BinanceFeed(DataFeed):
    def __init__(self, settings: FeedSettings, client: BinanceRestClient | None = None):
        self.settings = settings
        self.client = client or BinanceRestClient()
        self.poll_seconds = float(settings.options.get("poll_seconds", "5"))

    async def list_subjects(self) -> Sequence[SubjectDescriptor]:
        try:
            payload = await asyncio.to_thread(self.client.exchange_info)
            symbols = payload.get("symbols") if isinstance(payload, dict) else []
            if not isinstance(symbols, list):
                symbols = []
        except Exception:
            symbols = []

        if not symbols:
            return [
                SubjectDescriptor(
                    symbol="BTCUSDT",
                    display_name="BTC / USDT",
                    kinds=("tick", "candle"),
                    granularities=("1m", "5m", "15m", "1h"),
                    source="binance",
                    metadata={"fallback": True},
                )
            ]

        descriptors: list[SubjectDescriptor] = []
        for row in symbols[:500]:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").strip()
            if not symbol:
                continue
            descriptors.append(
                SubjectDescriptor(
                    symbol=symbol,
                    display_name=symbol,
                    kinds=("tick", "candle"),
                    granularities=("1m", "5m", "15m", "1h"),
                    source="binance",
                    metadata={
                        "status": row.get("status"),
                        "quote": row.get("quoteAsset"),
                        "base": row.get("baseAsset"),
                    },
                )
            )

        return descriptors

    async def listen(self, sub: FeedSubscription, sink: FeedSink) -> FeedHandle:
        async def _loop() -> None:
            watermark: dict[str, int] = {}
            while True:
                try:
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    req = FeedFetchRequest(
                        subjects=sub.subjects,
                        kind=sub.kind,
                        granularity=sub.granularity,
                        end_ts=now_ts,
                        limit=1,
                    )
                    records = await self.fetch(req)
                    for record in records:
                        last_ts = watermark.get(record.subject)
                        if last_ts is not None and record.ts_event <= last_ts:
                            continue
                        watermark[record.subject] = record.ts_event
                        await sink.on_record(record)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

                await asyncio.sleep(max(0.5, self.poll_seconds))

        task = asyncio.create_task(_loop())
        return _PollingFeedHandle(task)

    async def fetch(self, req: FeedFetchRequest) -> Sequence[FeedDataRecord]:
        if req.kind == "candle":
            records = await self._fetch_candles(req)
        else:
            records = await self._fetch_ticks(req)

        for subject in req.subjects:
            subject_count = sum(1 for r in records if r.subject == subject)
            if subject_count == 0:
                _logger.warning(
                    "Binance returned 0 records for subject=%r kind=%r granularity=%r. "
                    "Binance requires full pair symbols (e.g. BTCUSDT, not BTC).",
                    subject, req.kind, req.granularity,
                )

        return records

    async def _fetch_candles(self, req: FeedFetchRequest) -> list[FeedDataRecord]:
        records: list[FeedDataRecord] = []
        interval = _to_binance_interval(req.granularity)
        start_ms = int(req.start_ts * 1000) if req.start_ts is not None else None
        end_ms = int(req.end_ts * 1000) if req.end_ts is not None else None
        limit = req.limit or 500

        for asset in req.subjects:
            try:
                rows = await asyncio.to_thread(
                    self.client.klines,
                    asset,
                    interval,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    limit=limit,
                )
            except Exception:
                rows = []

            for row in rows:
                if not isinstance(row, list) or len(row) < 6:
                    continue
                try:
                    ts_event = int(row[0]) // 1000
                    record = FeedDataRecord(
                        subject=asset,
                        kind="candle",
                        granularity=req.granularity,
                        ts_event=ts_event,
                        values={
                            "open": float(row[1]),
                            "high": float(row[2]),
                            "low": float(row[3]),
                            "close": float(row[4]),
                            "volume": float(row[5]),
                        },
                        source="binance",
                    )
                except Exception:
                    continue
                records.append(record)

        return records

    async def _fetch_ticks(self, req: FeedFetchRequest) -> list[FeedDataRecord]:
        records: list[FeedDataRecord] = []
        now_ts = int(datetime.now(timezone.utc).timestamp())

        for asset in req.subjects:
            try:
                price = await asyncio.to_thread(self.client.ticker_price, asset)
            except Exception:
                continue

            records.append(
                FeedDataRecord(
                    subject=asset,
                    kind="tick",
                    granularity=req.granularity,
                    ts_event=now_ts,
                    values={"price": float(price)},
                    source="binance",
                )
            )

        return records


def build_binance_feed(settings: FeedSettings) -> BinanceFeed:
    return BinanceFeed(settings)


def _build_default_sdk_client(*, timeout_seconds: float) -> Any | None:
    if BinanceSDKClient is None:
        return None

    try:
        return BinanceSDKClient(
            api_key=None,
            api_secret=None,
            requests_params={"timeout": timeout_seconds},
            ping=False,
        )
    except Exception:
        return None


def _to_binance_interval(granularity: str) -> str:
    mapping = {
        "1s": "1m",
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
    }
    return mapping.get(str(granularity).strip(), "1m")
