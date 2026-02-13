from __future__ import annotations

from typing import Protocol, Sequence

from coordinator.feeds.contracts import (
    AssetDescriptor,
    FeedDataRecord,
    FeedFetchRequest,
    FeedSubscription,
)


class FeedSink(Protocol):
    async def on_record(self, record: FeedDataRecord) -> None: ...


class FeedHandle(Protocol):
    async def stop(self) -> None: ...


class DataFeed(Protocol):
    """Generic runtime data feed contract.

    - list_assets: provider-native discovery and capabilities
    - listen: push mode
    - fetch: pull mode (backfill + truth-window queries)
    """

    async def list_assets(self) -> Sequence[AssetDescriptor]: ...

    async def listen(self, sub: FeedSubscription, sink: FeedSink) -> FeedHandle: ...

    async def fetch(self, req: FeedFetchRequest) -> Sequence[FeedDataRecord]: ...
