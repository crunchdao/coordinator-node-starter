"""Paginated historical backfill service for market data feeds."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from coordinator.entities.market_record import MarketIngestionState, MarketRecord as DomainRecord
from coordinator.feeds.base import DataFeed
from coordinator.feeds.contracts import FeedFetchRequest, MarketRecord


@dataclass(frozen=True)
class BackfillRequest:
    provider: str
    assets: tuple[str, ...]
    kind: str
    granularity: str
    start: datetime
    end: datetime
    page_size: int = 500


@dataclass
class BackfillResult:
    records_written: int = 0
    pages_fetched: int = 0


class BackfillService:
    def __init__(self, feed: DataFeed, repository) -> None:
        self.feed = feed
        self.repository = repository
        self.logger = logging.getLogger(__name__)

    async def run(self, request: BackfillRequest) -> BackfillResult:
        result = BackfillResult()
        cursor_ts = int(request.start.timestamp())
        end_ts = int(request.end.timestamp())

        for asset in request.assets:
            asset_cursor = cursor_ts
            while asset_cursor < end_ts:
                req = FeedFetchRequest(
                    assets=(asset,),
                    kind=request.kind,
                    granularity=request.granularity,
                    start_ts=asset_cursor,
                    end_ts=end_ts,
                    limit=request.page_size,
                )

                records = await self.feed.fetch(req)
                result.pages_fetched += 1

                if not records:
                    break

                converted = [_feed_to_domain(request.provider, r) for r in records]
                written = self.repository.append_records(converted)
                result.records_written += written

                max_ts = max(r.ts_event for r in records)
                if max_ts <= asset_cursor:
                    break
                asset_cursor = max_ts + 1

                # Update watermark
                self.repository.set_watermark(
                    MarketIngestionState(
                        provider=request.provider,
                        asset=asset,
                        kind=request.kind,
                        granularity=request.granularity,
                        last_event_ts=datetime.fromtimestamp(max_ts, tz=timezone.utc),
                        meta={"phase": "backfill-manual"},
                    )
                )

                self.logger.info(
                    "backfill page asset=%s wrote=%d cursor=%s",
                    asset, written, datetime.fromtimestamp(asset_cursor, tz=timezone.utc).isoformat(),
                )

        return result


def _feed_to_domain(provider: str, record: MarketRecord) -> DomainRecord:
    return DomainRecord(
        provider=provider,
        asset=record.asset,
        kind=record.kind,
        granularity=record.granularity,
        ts_event=datetime.fromtimestamp(int(record.ts_event), tz=timezone.utc),
        values=dict(record.values),
        meta=dict(record.metadata),
    )
