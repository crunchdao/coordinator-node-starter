from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator_core.entities.market_record import MarketRecord
from coordinator_runtime.data_feeds import FeedFetchRequest, create_default_registry
from node_template.infrastructure.db.market_records_repository import DBMarketRecordRepository
from node_template.infrastructure.db.session import create_session

logger = logging.getLogger(__name__)


class InputService:
    """Reads feed data from DB, backfills from feed provider if needed."""

    def __init__(
        self,
        provider: str = "pyth",
        asset: str = "BTC",
        kind: str = "tick",
        granularity: str = "1s",
        window_size: int = 120,
    ):
        self.provider = provider
        self.asset = asset
        self.kind = kind
        self.granularity = granularity
        self.window_size = window_size

    @classmethod
    def from_env(cls) -> "InputService":
        assets_raw = os.getenv("FEED_ASSETS", "BTC")
        assets = [p.strip() for p in assets_raw.split(",") if p.strip()]
        return cls(
            provider=os.getenv("FEED_PROVIDER", "pyth").strip().lower(),
            asset=assets[0] if assets else "BTC",
            kind=os.getenv("FEED_KIND", "tick").strip().lower(),
            granularity=os.getenv("FEED_GRANULARITY", "1s").strip(),
            window_size=int(os.getenv("FEED_CANDLES_WINDOW", "120")),
        )

    def get_input(self, now: datetime) -> dict[str, Any]:
        """Provide raw input for this timestep."""
        candles = self._load_recent_candles(limit=self.window_size)

        if len(candles) < min(3, self.window_size):
            self._recover_window(
                start=now - timedelta(minutes=max(5, self.window_size)),
                end=now,
            )
            candles = self._load_recent_candles(limit=self.window_size)

        asof_ts = int(now.timestamp())
        if candles:
            asof_ts = int(candles[-1].get("ts", asof_ts))

        return {
            "symbol": self.asset,
            "asof_ts": asof_ts,
            "candles_1m": candles,
        }

    def get_ground_truth(self, performed_at: datetime, resolvable_at: datetime, asset: str | None = None) -> dict[str, Any] | None:
        """Look up what actually happened between prediction and resolution time."""
        asset = asset or self.asset

        entry_record = self._latest_record(at_or_before=performed_at)
        resolved_record = self._latest_record(at_or_before=resolvable_at)

        if entry_record is None or resolved_record is None:
            self._recover_window(
                start=performed_at - timedelta(minutes=10),
                end=resolvable_at + timedelta(minutes=2),
            )
            entry_record = self._latest_record(at_or_before=performed_at)
            resolved_record = self._latest_record(at_or_before=resolvable_at)

        if entry_record is None or resolved_record is None:
            return None

        entry_price = self._record_price(entry_record)
        resolved_price = self._record_price(resolved_record)
        if entry_price is None or resolved_price is None:
            return None

        return {
            "asset": asset,
            "entry_price": entry_price,
            "resolved_price": resolved_price,
            "resolved_market_time": self._ensure_utc(resolved_record.ts_event).isoformat(),
            "return_5m": (resolved_price - entry_price) / max(abs(entry_price), 1e-9),
            "y_up": resolved_price > entry_price,
            "source": self.provider,
        }

    # ── internals ──

    def _load_recent_candles(self, limit: int) -> list[dict[str, Any]]:
        with create_session() as session:
            repo = DBMarketRecordRepository(session)
            records = repo.fetch_records(
                provider=self.provider,
                asset=self.asset,
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
            repo = DBMarketRecordRepository(session)
            return repo.fetch_latest_record(
                provider=self.provider,
                asset=self.asset,
                kind=self.kind,
                granularity=self.granularity,
                at_or_before=self._ensure_utc(at_or_before),
            )

    def _recover_window(self, start: datetime, end: datetime) -> None:
        try:
            registry = create_default_registry()
            feed = registry.create(self.provider)
            request = FeedFetchRequest(
                assets=(self.asset,),
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
            repo = DBMarketRecordRepository(session)
            domain: list[MarketRecord] = []
            for row in records:
                ts_event = datetime.fromtimestamp(int(row.ts_event), tz=timezone.utc)
                domain.append(MarketRecord(
                    provider=row.source or self.provider,
                    asset=row.asset,
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
