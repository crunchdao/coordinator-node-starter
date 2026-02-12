from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MarketRecord:
    provider: str
    asset: str
    kind: str
    granularity: str
    ts_event: datetime
    values: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)
    ts_ingested: datetime = field(default_factory=_utc_now)


@dataclass
class MarketIngestionState:
    provider: str
    asset: str
    kind: str
    granularity: str
    last_event_ts: datetime | None
    meta: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=_utc_now)
