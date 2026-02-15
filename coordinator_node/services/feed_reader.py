from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator_node.entities.feed_record import FeedRecord
from coordinator_node.feeds import FeedFetchRequest, create_default_registry
from coordinator_node.db.feed_records import DBFeedRecordRepository
from coordinator_node.db.session import create_session

logger = logging.getLogger(__name__)


class FeedReader:
    """Reads feed data from DB, backfills from feed provider if needed."""

    def __init__(
        self,
        source: str = "pyth",
        subject: str = "BTC",
        kind: str = "tick",
        granularity: str = "1s",
        window_size: int = 120,
    ):
        self.source = source
        self.subject = subject
        self.kind = kind
        self.granularity = granularity
        self.window_size = window_size

    @classmethod
    def from_env(cls) -> "FeedReader":
        subjects_raw = os.getenv("FEED_SUBJECTS", os.getenv("FEED_ASSETS", "BTC"))
        subjects = [p.strip() for p in subjects_raw.split(",") if p.strip()]
        return cls(
            source=os.getenv("FEED_SOURCE", os.getenv("FEED_PROVIDER", "pyth")).strip().lower(),
            subject=subjects[0] if subjects else "BTC",
            kind=os.getenv("FEED_KIND", "tick").strip().lower(),
            granularity=os.getenv("FEED_GRANULARITY", "1s").strip(),
            window_size=int(os.getenv("FEED_CANDLES_WINDOW", "120")),
        )

    # Multi-timeframe settings: (target_minutes, window_count)
    MULTI_TF = [
        (5, 60),    # 5m candles, last 60 → 5 hours
        (15, 40),   # 15m candles, last 40 → 10 hours
        (60, 24),   # 1h candles, last 24 → 1 day
    ]

    def get_input(self, now: datetime) -> dict[str, Any]:
        """Build raw input dict for this timestep from recent feed records.

        Returns candle data at multiple timeframes aggregated from 1m candles:
        candles_1m, candles_5m, candles_15m, candles_1h.
        """
        # Load enough 1m candles to cover the largest multi-TF window (24h = 1440m)
        max_1m_needed = max(tf * count for tf, count in self.MULTI_TF)
        load_limit = max(self.window_size, max_1m_needed)

        candles = self._load_recent_candles(limit=load_limit)

        if len(candles) < min(3, self.window_size):
            self._recover_window(
                start=now - timedelta(minutes=max(5, load_limit)),
                end=now,
            )
            candles = self._load_recent_candles(limit=load_limit)

        asof_ts = int(now.timestamp())
        if candles:
            asof_ts = int(candles[-1].get("ts", asof_ts))

        result = {
            "symbol": self.subject,
            "asof_ts": asof_ts,
            "candles_1m": candles[-self.window_size:],
        }

        # Aggregate higher timeframes from 1m candles
        for target_minutes, window_count in self.MULTI_TF:
            key = f"candles_{target_minutes}m" if target_minutes < 60 else f"candles_{target_minutes // 60}h"
            result[key] = self._aggregate_candles(candles, target_minutes, window_count)

        # Attach microstructure data (order book + funding) if available
        result["orderbook"] = self._load_latest_microstructure("depth")
        result["funding"] = self._load_latest_microstructure("funding")

        return result

    def fetch_window(
        self,
        start: datetime,
        end: datetime,
        source: str | None = None,
        subject: str | None = None,
        kind: str | None = None,
        granularity: str | None = None,
    ) -> list[FeedRecord]:
        """Fetch feed records in a time window. Falls back to instance defaults for any missing dimension."""
        source = source or self.source
        subject = subject or self.subject
        kind = kind or self.kind
        granularity = granularity or self.granularity

        with create_session() as session:
            repo = DBFeedRecordRepository(session)
            records = repo.fetch_records(
                source=source,
                subject=subject,
                kind=kind,
                granularity=granularity,
                start_ts=self._ensure_utc(start),
                end_ts=self._ensure_utc(end),
            )

        if not records:
            self._recover_window(start=start - timedelta(minutes=2), end=end + timedelta(minutes=2))
            with create_session() as session:
                repo = DBFeedRecordRepository(session)
                records = repo.fetch_records(
                    source=source,
                    subject=subject,
                    kind=kind,
                    granularity=granularity,
                    start_ts=self._ensure_utc(start),
                    end_ts=self._ensure_utc(end),
                )

        return records

    # ── internals ──

    def _load_recent_candles(self, limit: int) -> list[dict[str, Any]]:
        with create_session() as session:
            repo = DBFeedRecordRepository(session)
            records = repo.fetch_records(
                source=self.source,
                subject=self.subject,
                kind=self.kind,
                granularity=self.granularity,
                limit=max(1, limit),
            )

        candles: list[dict[str, Any]] = []
        for record in records[-max(1, limit):]:
            price = self._record_price(record)
            if price is None:
                continue
            ts_event = int(self._ensure_utc(record.ts_event).timestamp())

            if record.kind == "candle":
                values = record.values or {}
                candles.append({
                    "ts": ts_event,
                    "open": float(values.get("open", price)),
                    "high": float(values.get("high", price)),
                    "low": float(values.get("low", price)),
                    "close": float(values.get("close", price)),
                    "volume": float(values.get("volume", 0.0)),
                })
            else:
                candles.append({
                    "ts": ts_event,
                    "open": price, "high": price,
                    "low": price, "close": price,
                    "volume": 0.0,
                })
        return candles

    def _latest_record(self, at_or_before: datetime) -> Any:
        with create_session() as session:
            repo = DBFeedRecordRepository(session)
            return repo.fetch_latest_record(
                source=self.source,
                subject=self.subject,
                kind=self.kind,
                granularity=self.granularity,
                at_or_before=self._ensure_utc(at_or_before),
            )

    def _recover_window(self, start: datetime, end: datetime) -> None:
        try:
            registry = create_default_registry()
            feed = registry.create(self.source)
            request = FeedFetchRequest(
                subjects=(self.subject,),
                kind=self.kind if self.kind in {"tick", "candle"} else "tick",
                granularity=self.granularity,
                start_ts=int(self._ensure_utc(start).timestamp()),
                end_ts=int(self._ensure_utc(end).timestamp()),
                limit=500,
            )
            records = self._run_async(feed.fetch(request))
        except Exception:
            return

        if not records:
            return

        with create_session() as session:
            repo = DBFeedRecordRepository(session)
            domain: list[FeedRecord] = []
            for row in records:
                ts_event = datetime.fromtimestamp(int(row.ts_event), tz=timezone.utc)
                domain.append(FeedRecord(
                    source=row.source or self.source,
                    subject=row.subject,
                    kind=row.kind,
                    granularity=row.granularity,
                    ts_event=ts_event,
                    values=dict(row.values),
                    meta=dict(row.metadata),
                    ts_ingested=datetime.now(timezone.utc),
                ))
            if domain:
                repo.append_records(domain)

    @staticmethod
    def _run_async(coro: Any) -> list:
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(coro)
            if loop.is_running():
                try:
                    coro.close()
                except Exception:
                    pass
                return []
            return loop.run_until_complete(coro)
        except Exception:
            return []

    def _load_latest_microstructure(self, kind: str) -> dict[str, Any] | None:
        """Load the most recent depth or funding record for this subject."""
        try:
            with create_session() as session:
                repo = DBFeedRecordRepository(session)
                records = repo.fetch_records(
                    source=self.source,
                    subject=self.subject,
                    kind=kind,
                    granularity=self.granularity,
                    limit=1,
                )
            if records:
                return records[-1].values or None
        except Exception:
            pass
        return None

    @staticmethod
    def _aggregate_candles(
        candles_1m: list[dict[str, Any]],
        target_minutes: int,
        max_output: int,
    ) -> list[dict[str, Any]]:
        """Roll up 1m candles into higher-timeframe OHLCV bars.

        Groups by flooring each candle's timestamp to the target interval boundary.
        Returns at most *max_output* bars, most-recent last.
        """
        if not candles_1m or target_minutes <= 1:
            return candles_1m[-max_output:] if candles_1m else []

        interval_s = target_minutes * 60
        buckets: dict[int, dict[str, Any]] = {}

        for c in candles_1m:
            ts = c.get("ts", 0)
            bucket_ts = (ts // interval_s) * interval_s

            if bucket_ts not in buckets:
                buckets[bucket_ts] = {
                    "ts": bucket_ts,
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c["volume"],
                }
            else:
                bar = buckets[bucket_ts]
                bar["high"] = max(bar["high"], c["high"])
                bar["low"] = min(bar["low"], c["low"])
                bar["close"] = c["close"]
                bar["volume"] += c["volume"]

        sorted_bars = sorted(buckets.values(), key=lambda b: b["ts"])
        return sorted_bars[-max_output:]

    @staticmethod
    def _record_price(record) -> float | None:
        values = record.values or {}
        for key in ("close", "price"):
            if key in values:
                try:
                    return float(values[key])
                except Exception:
                    return None
        return None

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
