from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MarketDataKind = Literal["tick", "candle"]


@dataclass(frozen=True)
class AssetDescriptor:
    """Provider-native asset descriptor with per-asset capabilities."""

    symbol: str
    display_name: str | None
    kinds: tuple[MarketDataKind, ...]
    granularities: tuple[str, ...]
    quote: str | None
    base: str | None
    venue: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FeedSubscription:
    """Push/listen mode subscription request."""

    assets: tuple[str, ...]
    kind: MarketDataKind
    granularity: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeedFetchRequest:
    """Pull/fetch mode request used for backfill and truth windows."""

    assets: tuple[str, ...]
    kind: MarketDataKind
    granularity: str
    start_ts: int | None = None
    end_ts: int | None = None
    limit: int | None = None
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketRecord:
    """Canonical market record shape normalized by feed adapters."""

    asset: str
    kind: MarketDataKind
    granularity: str
    ts_event: int
    values: dict[str, Any]
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)
