from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Iterable

from sqlalchemy import func
from sqlmodel import Session, delete, select

from coordinator.entities.market_record import MarketIngestionState, MarketRecord
from coordinator.db.tables import MarketIngestionStateRow, MarketRecordRow


class DBMarketRecordRepository:
    def __init__(self, session: Session):
        self._session = session

    def rollback(self) -> None:
        self._session.rollback()

    def append_records(self, records: Iterable[MarketRecord]) -> int:
        count = 0
        for record in records:
            row = self._domain_to_row(record)
            existing = self._session.get(MarketRecordRow, row.id)

            if existing is None:
                self._session.add(row)
            else:
                existing.values_jsonb = row.values_jsonb
                existing.meta_jsonb = row.meta_jsonb
                existing.ts_ingested = row.ts_ingested

            count += 1

        self._session.commit()
        return count

    def fetch_records(
        self,
        *,
        provider: str,
        asset: str,
        kind: str,
        granularity: str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
        limit: int | None = None,
    ) -> list[MarketRecord]:
        stmt = (
            select(MarketRecordRow)
            .where(MarketRecordRow.provider == provider)
            .where(MarketRecordRow.asset == asset)
            .where(MarketRecordRow.kind == kind)
            .where(MarketRecordRow.granularity == granularity)
            .order_by(MarketRecordRow.ts_event.asc())
        )

        if start_ts is not None:
            stmt = stmt.where(MarketRecordRow.ts_event >= start_ts)
        if end_ts is not None:
            stmt = stmt.where(MarketRecordRow.ts_event <= end_ts)
        if limit is not None:
            stmt = stmt.limit(max(0, int(limit)))

        rows = self._session.exec(stmt).all()
        return [self._row_to_domain(row) for row in rows]

    def prune_market_time_before(self, cutoff_ts: datetime) -> int:
        rows = self._session.exec(
            select(MarketRecordRow.id).where(MarketRecordRow.ts_event < cutoff_ts)
        ).all()
        deleted = len(rows)

        if deleted:
            self._session.exec(delete(MarketRecordRow).where(MarketRecordRow.ts_event < cutoff_ts))
            self._session.commit()

        return deleted

    def fetch_latest_record(
        self,
        *,
        provider: str,
        asset: str,
        kind: str,
        granularity: str,
        at_or_before: datetime | None = None,
    ) -> MarketRecord | None:
        stmt = (
            select(MarketRecordRow)
            .where(MarketRecordRow.provider == provider)
            .where(MarketRecordRow.asset == asset)
            .where(MarketRecordRow.kind == kind)
            .where(MarketRecordRow.granularity == granularity)
            .order_by(MarketRecordRow.ts_event.desc())
            .limit(1)
        )

        if at_or_before is not None:
            stmt = stmt.where(MarketRecordRow.ts_event <= at_or_before)

        row = self._session.exec(stmt).first()
        return self._row_to_domain(row) if row is not None else None

    def list_indexed_feeds(self) -> list[dict[str, object]]:
        grouped_rows = self._session.exec(
            select(
                MarketRecordRow.provider,
                MarketRecordRow.asset,
                MarketRecordRow.kind,
                MarketRecordRow.granularity,
                func.count(MarketRecordRow.id),
                func.min(MarketRecordRow.ts_event),
                func.max(MarketRecordRow.ts_event),
            )
            .group_by(
                MarketRecordRow.provider,
                MarketRecordRow.asset,
                MarketRecordRow.kind,
                MarketRecordRow.granularity,
            )
            .order_by(
                MarketRecordRow.provider.asc(),
                MarketRecordRow.asset.asc(),
                MarketRecordRow.kind.asc(),
                MarketRecordRow.granularity.asc(),
            )
        ).all()

        watermarks = {
            (row.provider, row.asset, row.kind, row.granularity): row
            for row in self._session.exec(select(MarketIngestionStateRow)).all()
        }

        summaries: list[dict[str, object]] = []
        for provider, asset, kind, granularity, count, oldest_ts, newest_ts in grouped_rows:
            key = (provider, asset, kind, granularity)
            state = watermarks.get(key)
            summaries.append(
                {
                    "provider": provider,
                    "asset": asset,
                    "kind": kind,
                    "granularity": granularity,
                    "record_count": int(count or 0),
                    "oldest_ts": _ensure_utc(oldest_ts).isoformat() if oldest_ts is not None else None,
                    "newest_ts": _ensure_utc(newest_ts).isoformat() if newest_ts is not None else None,
                    "watermark_ts": (
                        _ensure_utc(state.last_event_ts).isoformat()
                        if state is not None and state.last_event_ts is not None
                        else None
                    ),
                    "watermark_updated_at": (
                        _ensure_utc(state.updated_at).isoformat()
                        if state is not None and state.updated_at is not None
                        else None
                    ),
                }
            )

        return summaries

    def tail_records(
        self,
        *,
        provider: str | None = None,
        asset: str | None = None,
        kind: str | None = None,
        granularity: str | None = None,
        limit: int = 20,
    ) -> list[MarketRecord]:
        stmt = select(MarketRecordRow).order_by(MarketRecordRow.ts_event.desc())

        if provider:
            stmt = stmt.where(MarketRecordRow.provider == provider)
        if asset:
            stmt = stmt.where(MarketRecordRow.asset == asset)
        if kind:
            stmt = stmt.where(MarketRecordRow.kind == kind)
        if granularity:
            stmt = stmt.where(MarketRecordRow.granularity == granularity)

        stmt = stmt.limit(max(1, int(limit)))

        rows = self._session.exec(stmt).all()
        return [self._row_to_domain(row) for row in rows]

    def get_watermark(
        self,
        *,
        provider: str,
        asset: str,
        kind: str,
        granularity: str,
    ) -> MarketIngestionState | None:
        row = self._session.get(MarketIngestionStateRow, _watermark_id(provider, asset, kind, granularity))
        if row is None:
            return None
        return self._watermark_row_to_domain(row)

    def set_watermark(self, state: MarketIngestionState) -> None:
        row = self._watermark_domain_to_row(state)
        existing = self._session.get(MarketIngestionStateRow, row.id)

        if existing is None:
            self._session.add(row)
        else:
            existing.last_event_ts = row.last_event_ts
            existing.meta_jsonb = row.meta_jsonb
            existing.updated_at = row.updated_at

        self._session.commit()

    @staticmethod
    def _domain_to_row(record: MarketRecord) -> MarketRecordRow:
        normalized_ts_event = _ensure_utc(record.ts_event)
        normalized_ts_ingested = _ensure_utc(record.ts_ingested)

        return MarketRecordRow(
            id=_record_id(record.provider, record.asset, record.kind, record.granularity, normalized_ts_event),
            provider=record.provider,
            asset=record.asset,
            kind=record.kind,
            granularity=record.granularity,
            ts_event=normalized_ts_event,
            ts_ingested=normalized_ts_ingested,
            values_jsonb=dict(record.values),
            meta_jsonb=dict(record.meta),
        )

    @staticmethod
    def _row_to_domain(row: MarketRecordRow) -> MarketRecord:
        return MarketRecord(
            provider=row.provider,
            asset=row.asset,
            kind=row.kind,
            granularity=row.granularity,
            ts_event=_ensure_utc(row.ts_event),
            ts_ingested=_ensure_utc(row.ts_ingested),
            values=dict(row.values_jsonb or {}),
            meta=dict(row.meta_jsonb or {}),
        )

    @staticmethod
    def _watermark_domain_to_row(state: MarketIngestionState) -> MarketIngestionStateRow:
        return MarketIngestionStateRow(
            id=_watermark_id(state.provider, state.asset, state.kind, state.granularity),
            provider=state.provider,
            asset=state.asset,
            kind=state.kind,
            granularity=state.granularity,
            last_event_ts=_ensure_utc(state.last_event_ts) if state.last_event_ts is not None else None,
            updated_at=_ensure_utc(state.updated_at),
            meta_jsonb=dict(state.meta),
        )

    @staticmethod
    def _watermark_row_to_domain(row: MarketIngestionStateRow) -> MarketIngestionState:
        return MarketIngestionState(
            provider=row.provider,
            asset=row.asset,
            kind=row.kind,
            granularity=row.granularity,
            last_event_ts=_ensure_utc(row.last_event_ts) if row.last_event_ts is not None else None,
            updated_at=_ensure_utc(row.updated_at),
            meta=dict(row.meta_jsonb or {}),
        )


def _watermark_id(provider: str, asset: str, kind: str, granularity: str) -> str:
    return f"{provider}:{asset}:{kind}:{granularity}"


def _record_id(provider: str, asset: str, kind: str, granularity: str, ts_event: datetime) -> str:
    fingerprint = f"{provider}|{asset}|{kind}|{granularity}|{_ensure_utc(ts_event).isoformat()}"
    return hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()  # noqa: S324


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
