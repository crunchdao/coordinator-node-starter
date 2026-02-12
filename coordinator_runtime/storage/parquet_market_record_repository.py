from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from coordinator_core.entities.market_record import MarketIngestionState, MarketRecord
from coordinator_core.services.interfaces.market_record_repository import MarketRecordRepository


class ParquetMarketRecordRepository(MarketRecordRepository):
    """Future cold-storage adapter for market tape in parquet files.

    This class intentionally remains a stub for now while Postgres is the
    canonical store. The interface is present so callers can depend on the
    same contract once parquet archival lands.
    """

    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path)

    def append_records(self, records: Iterable[MarketRecord]) -> int:
        raise NotImplementedError("Parquet market record storage is not implemented yet")

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
        raise NotImplementedError("Parquet market record storage is not implemented yet")

    def prune_market_time_before(self, cutoff_ts: datetime) -> int:
        raise NotImplementedError("Parquet market record storage is not implemented yet")

    def fetch_latest_record(
        self,
        *,
        provider: str,
        asset: str,
        kind: str,
        granularity: str,
        at_or_before: datetime | None = None,
    ) -> MarketRecord | None:
        raise NotImplementedError("Parquet market record storage is not implemented yet")

    def list_indexed_feeds(self) -> list[dict[str, object]]:
        raise NotImplementedError("Parquet market record storage is not implemented yet")

    def tail_records(
        self,
        *,
        provider: str | None = None,
        asset: str | None = None,
        kind: str | None = None,
        granularity: str | None = None,
        limit: int = 20,
    ) -> list[MarketRecord]:
        raise NotImplementedError("Parquet market record storage is not implemented yet")

    def get_watermark(self, *, provider: str, asset: str, kind: str, granularity: str) -> MarketIngestionState | None:
        raise NotImplementedError("Parquet market record storage is not implemented yet")

    def set_watermark(self, state: MarketIngestionState) -> None:
        raise NotImplementedError("Parquet market record storage is not implemented yet")
