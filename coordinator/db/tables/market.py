"""Market data ingestion tables."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketRecordRow(SQLModel, table=True):
    __tablename__ = "market_records"

    id: str = Field(primary_key=True)

    provider: str = Field(index=True)
    asset: str = Field(index=True)
    kind: str = Field(index=True)
    granularity: str = Field(index=True)

    ts_event: datetime = Field(index=True)
    ts_ingested: datetime = Field(default_factory=utc_now, index=True)

    values_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )

    __table_args__ = (
        Index(
            "uq_market_records_event",
            "provider", "asset", "kind", "granularity", "ts_event",
            unique=True,
        ),
    )


class MarketIngestionStateRow(SQLModel, table=True):
    __tablename__ = "market_ingestion_state"

    id: str = Field(primary_key=True)

    provider: str = Field(index=True)
    asset: str = Field(index=True)
    kind: str = Field(index=True)
    granularity: str = Field(index=True)

    last_event_ts: Optional[datetime] = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)

    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )

    __table_args__ = (
        Index(
            "uq_market_ingestion_scope",
            "provider", "asset", "kind", "granularity",
            unique=True,
        ),
    )
