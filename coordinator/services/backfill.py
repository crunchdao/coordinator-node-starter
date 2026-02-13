"""Paginated historical backfill service for data feeds."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from coordinator.entities.feed_record import FeedIngestionState, FeedRecord
from coordinator.feeds.base import DataFeed
from coordinator.feeds.contracts import FeedDataRecord, FeedFetchRequest


@dataclass(frozen=True)
class BackfillRequest:
    source: str
    subjects: tuple[str, ...]
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

        for subject in request.subjects:
            subject_cursor = cursor_ts
            while subject_cursor < end_ts:
                req = FeedFetchRequest(
                    assets=(subject,),
                    kind=request.kind,
                    granularity=request.granularity,
                    start_ts=subject_cursor,
                    end_ts=end_ts,
                    limit=request.page_size,
                )

                records = await self.feed.fetch(req)
                result.pages_fetched += 1

                if not records:
                    break

                converted = [_feed_to_domain(request.source, r) for r in records]
                written = self.repository.append_records(converted)
                result.records_written += written

                max_ts = max(r.ts_event for r in records)
                if max_ts <= subject_cursor:
                    break
                subject_cursor = max_ts + 1

                self.repository.set_watermark(
                    FeedIngestionState(
                        source=request.source,
                        subject=subject,
                        kind=request.kind,
                        granularity=request.granularity,
                        last_event_ts=datetime.fromtimestamp(max_ts, tz=timezone.utc),
                        meta={"phase": "backfill-manual"},
                    )
                )

                self.logger.info(
                    "backfill page subject=%s wrote=%d cursor=%s",
                    subject, written, datetime.fromtimestamp(subject_cursor, tz=timezone.utc).isoformat(),
                )

        return result


def _feed_to_domain(source: str, record: FeedDataRecord) -> FeedRecord:
    return FeedRecord(
        source=source,
        subject=record.subject,
        kind=record.kind,
        granularity=record.granularity,
        ts_event=datetime.fromtimestamp(int(record.ts_event), tz=timezone.utc),
        values=dict(record.values),
        meta=dict(record.metadata),
    )
