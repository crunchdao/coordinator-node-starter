from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from coordinator_core.entities.market_record import MarketIngestionState, MarketRecord
from coordinator_runtime.data_feeds import (
    FeedFetchRequest,
    FeedSubscription,
    MarketRecord as FeedMarketRecord,
    create_default_registry,
)


@dataclass(frozen=True)
class MarketDataSettings:
    provider: str
    assets: tuple[str, ...]
    kind: str
    granularity: str
    poll_seconds: float
    backfill_minutes: int
    ttl_days: int
    retention_check_seconds: int

    @classmethod
    def from_env(cls) -> "MarketDataSettings":
        assets_raw = os.getenv("FEED_ASSETS", "BTC")
        assets = tuple(part.strip() for part in assets_raw.split(",") if part.strip())

        return cls(
            provider=os.getenv("FEED_PROVIDER", "pyth").strip().lower(),
            assets=assets or ("BTC",),
            kind=os.getenv("FEED_KIND", "tick").strip().lower(),
            granularity=os.getenv("FEED_GRANULARITY", "1s").strip(),
            poll_seconds=float(os.getenv("FEED_POLL_SECONDS", "5")),
            backfill_minutes=int(os.getenv("FEED_BACKFILL_MINUTES", "180")),
            ttl_days=int(os.getenv("MARKET_RECORD_TTL_DAYS", "90")),
            retention_check_seconds=int(os.getenv("MARKET_RETENTION_CHECK_SECONDS", "3600")),
        )


class MarketDataService:
    def __init__(
        self,
        settings: MarketDataSettings,
        market_record_repository,
    ):
        self.settings = settings
        self.market_record_repository = market_record_repository
        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()
        self._handles = []

    async def run(self) -> None:
        self.logger.info(
            "market data service started provider=%s assets=%s kind=%s granularity=%s",
            self.settings.provider,
            ",".join(self.settings.assets),
            self.settings.kind,
            self.settings.granularity,
        )

        registry = create_default_registry()
        feed = registry.create_from_env(default_provider=self.settings.provider)

        await self._backfill(feed)

        sink = _RepositorySink(self.market_record_repository)
        subscription = FeedSubscription(
            assets=self.settings.assets,
            kind=self.settings.kind if self.settings.kind in {"tick", "candle"} else "tick",
            granularity=self.settings.granularity,
        )
        handle = await feed.listen(subscription, sink)
        self._handles.append(handle)

        retention_task = asyncio.create_task(self._retention_loop())

        try:
            await self.stop_event.wait()
        finally:
            retention_task.cancel()
            for item in self._handles:
                try:
                    await item.stop()
                except Exception:
                    pass

    async def shutdown(self) -> None:
        self.stop_event.set()

    async def _backfill(self, feed) -> None:
        now = datetime.now(timezone.utc)

        for asset in self.settings.assets:
            watermark = self.market_record_repository.get_watermark(
                provider=self.settings.provider,
                asset=asset,
                kind=self.settings.kind,
                granularity=self.settings.granularity,
            )

            start = (
                watermark.last_event_ts
                if watermark is not None and watermark.last_event_ts is not None
                else now - timedelta(minutes=max(1, self.settings.backfill_minutes))
            )

            req = FeedFetchRequest(
                assets=(asset,),
                kind=self.settings.kind if self.settings.kind in {"tick", "candle"} else "tick",
                granularity=self.settings.granularity,
                start_ts=int(start.timestamp()),
                end_ts=int(now.timestamp()),
                limit=500,
            )

            records = await feed.fetch(req)
            written = self._append_feed_records(records)
            if written:
                latest_ts = max(record.ts_event for record in records)
                self.market_record_repository.set_watermark(
                    MarketIngestionState(
                        provider=self.settings.provider,
                        asset=asset,
                        kind=self.settings.kind,
                        granularity=self.settings.granularity,
                        last_event_ts=datetime.fromtimestamp(latest_ts, tz=timezone.utc),
                        meta={"phase": "backfill"},
                    )
                )
                self.logger.info("backfill asset=%s wrote=%d", asset, written)

    async def _retention_loop(self) -> None:
        while not self.stop_event.is_set():
            cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, self.settings.ttl_days))
            try:
                deleted = self.market_record_repository.prune_market_time_before(cutoff)
                if deleted:
                    self.logger.info("market record retention pruned=%d cutoff=%s", deleted, cutoff.isoformat())
            except Exception as exc:
                self.logger.warning("market record retention failed: %s", exc)

            try:
                await asyncio.wait_for(
                    self.stop_event.wait(),
                    timeout=max(30, self.settings.retention_check_seconds),
                )
            except asyncio.TimeoutError:
                pass

    def _append_feed_records(self, records: Sequence[FeedMarketRecord]) -> int:
        if not records:
            return 0

        converted = [_feed_to_domain(self.settings.provider, record) for record in records]
        return self.market_record_repository.append_records(converted)


class _RepositorySink:
    def __init__(self, repository):
        self._repository = repository

    async def on_record(self, record: FeedMarketRecord) -> None:
        domain = _feed_to_domain(record.source, record)
        self._repository.append_records([domain])
        self._repository.set_watermark(
            MarketIngestionState(
                provider=record.source,
                asset=record.asset,
                kind=record.kind,
                granularity=record.granularity,
                last_event_ts=datetime.fromtimestamp(record.ts_event, tz=timezone.utc),
                meta={"phase": "listen"},
            )
        )
        try:
            from node_template.infrastructure.db.pg_notify import notify
            notify()
        except Exception:
            pass


def _feed_to_domain(default_provider: str, record: FeedMarketRecord) -> MarketRecord:
    provider = record.source or default_provider
    return MarketRecord(
        provider=provider,
        asset=record.asset,
        kind=record.kind,
        granularity=record.granularity,
        ts_event=datetime.fromtimestamp(int(record.ts_event), tz=timezone.utc),
        values=dict(record.values),
        meta=dict(record.metadata),
    )
