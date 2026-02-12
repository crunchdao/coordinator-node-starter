from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Iterable

from coordinator.entities.market_record import MarketIngestionState, MarketRecord


class MarketRecordRepository(ABC):
    @abstractmethod
    def append_records(self, records: Iterable[MarketRecord]) -> int:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def prune_market_time_before(self, cutoff_ts: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    def fetch_latest_record(
        self,
        *,
        provider: str,
        asset: str,
        kind: str,
        granularity: str,
        at_or_before: datetime | None = None,
    ) -> MarketRecord | None:
        raise NotImplementedError

    @abstractmethod
    def list_indexed_feeds(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def tail_records(
        self,
        *,
        provider: str | None = None,
        asset: str | None = None,
        kind: str | None = None,
        granularity: str | None = None,
        limit: int = 20,
    ) -> list[MarketRecord]:
        raise NotImplementedError

    @abstractmethod
    def get_watermark(self, *, provider: str, asset: str, kind: str, granularity: str) -> MarketIngestionState | None:
        raise NotImplementedError

    @abstractmethod
    def set_watermark(self, state: MarketIngestionState) -> None:
        raise NotImplementedError
