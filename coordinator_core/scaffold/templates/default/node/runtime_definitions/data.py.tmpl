from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from typing import Any

from coordinator_core.entities.market_record import MarketRecord
from coordinator_runtime.data_feeds import FeedFetchRequest, create_default_registry
from node_template.infrastructure.db.market_records_repository import DBMarketRecordRepository
from node_template.infrastructure.db.session import create_session


def provide_raw_input(now):
    asset = _default_asset()
    provider = _feed_provider()
    kind = _feed_kind()
    granularity = _feed_granularity()
    window_size = _candles_window_size()

    candles = _load_recent_candles(
        provider=provider,
        asset=asset,
        kind=kind,
        granularity=granularity,
        limit=window_size,
    )

    if len(candles) < min(3, window_size):
        _recover_window(
            provider=provider,
            asset=asset,
            kind=kind,
            granularity=granularity,
            start=now - timedelta(minutes=max(5, window_size)),
            end=now,
        )
        candles = _load_recent_candles(
            provider=provider,
            asset=asset,
            kind=kind,
            granularity=granularity,
            limit=window_size,
        )

    asof_ts = int(now.timestamp())
    if candles:
        asof_ts = int(candles[-1].get("ts", asof_ts))

    return {
        "symbol": asset,
        "asof_ts": asof_ts,
        "horizon_minutes": 5,
        "candles_1m": candles,
    }


def resolve_ground_truth(prediction):
    provider = _feed_provider()
    kind = _feed_kind()
    granularity = _feed_granularity()

    scope = getattr(prediction, "scope", {}) or {}
    asset = str(scope.get("asset") or _default_asset())

    performed_at = _ensure_utc(getattr(prediction, "performed_at", datetime.now(timezone.utc)))
    resolvable_at = _ensure_utc(getattr(prediction, "resolvable_at", datetime.now(timezone.utc)))

    entry_record = _latest_record(
        provider=provider,
        asset=asset,
        kind=kind,
        granularity=granularity,
        at_or_before=performed_at,
    )
    resolved_record = _latest_record(
        provider=provider,
        asset=asset,
        kind=kind,
        granularity=granularity,
        at_or_before=resolvable_at,
    )

    if entry_record is None or resolved_record is None:
        _recover_window(
            provider=provider,
            asset=asset,
            kind=kind,
            granularity=granularity,
            start=performed_at - timedelta(minutes=10),
            end=resolvable_at + timedelta(minutes=2),
        )
        entry_record = _latest_record(
            provider=provider,
            asset=asset,
            kind=kind,
            granularity=granularity,
            at_or_before=performed_at,
        )
        resolved_record = _latest_record(
            provider=provider,
            asset=asset,
            kind=kind,
            granularity=granularity,
            at_or_before=resolvable_at,
        )

    if entry_record is None or resolved_record is None:
        return None

    entry_price = _record_price(entry_record)
    resolved_price = _record_price(resolved_record)
    if entry_price is None or resolved_price is None:
        return None

    return {
        "asset": asset,
        "entry_price": entry_price,
        "resolved_price": resolved_price,
        "resolved_market_time": _ensure_utc(resolved_record.ts_event).isoformat(),
        "return_5m": (resolved_price - entry_price) / max(abs(entry_price), 1e-9),
        "y_up": resolved_price > entry_price,
        "source": provider,
    }


def _load_recent_candles(
    *,
    provider: str,
    asset: str,
    kind: str,
    granularity: str,
    limit: int,
) -> list[dict[str, Any]]:
    with create_session() as session:
        repository = DBMarketRecordRepository(session)
        records = repository.fetch_records(
            provider=provider,
            asset=asset,
            kind=kind,
            granularity=granularity,
            limit=max(1, int(limit)),
        )

    candles: list[dict[str, Any]] = []
    for record in records[-max(1, int(limit)) :]:
        price = _record_price(record)
        if price is None:
            continue
        ts_event = int(_ensure_utc(record.ts_event).timestamp())

        if record.kind == "candle":
            values = record.values or {}
            candles.append(
                {
                    "ts": ts_event,
                    "open": float(values.get("open", price)),
                    "high": float(values.get("high", price)),
                    "low": float(values.get("low", price)),
                    "close": float(values.get("close", price)),
                    "volume": float(values.get("volume", 0.0)),
                }
            )
            continue

        candles.append(
            {
                "ts": ts_event,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0.0,
            }
        )

    return candles


def _latest_record(
    *,
    provider: str,
    asset: str,
    kind: str,
    granularity: str,
    at_or_before: datetime,
):
    with create_session() as session:
        repository = DBMarketRecordRepository(session)
        return repository.fetch_latest_record(
            provider=provider,
            asset=asset,
            kind=kind,
            granularity=granularity,
            at_or_before=_ensure_utc(at_or_before),
        )


def _recover_window(
    *,
    provider: str,
    asset: str,
    kind: str,
    granularity: str,
    start: datetime,
    end: datetime,
) -> None:
    try:
        registry = create_default_registry()
        feed = registry.create(provider)
        request = FeedFetchRequest(
            assets=(asset,),
            kind=kind if kind in {"tick", "candle"} else "tick",
            granularity=granularity,
            start_ts=int(_ensure_utc(start).timestamp()),
            end_ts=int(_ensure_utc(end).timestamp()),
            limit=500,
        )
        records = _run_async(feed.fetch(request))
    except Exception:
        return

    if not records:
        return

    with create_session() as session:
        repository = DBMarketRecordRepository(session)
        domain: list[MarketRecord] = []
        for row in records:
            ts_event = datetime.fromtimestamp(int(row.ts_event), tz=timezone.utc)
            domain.append(
                MarketRecord(
                    provider=row.source or provider,
                    asset=row.asset,
                    kind=row.kind,
                    granularity=row.granularity,
                    ts_event=ts_event,
                    values=dict(row.values),
                    meta=dict(row.metadata),
                    ts_ingested=datetime.now(timezone.utc),
                )
            )

        if domain:
            repository.append_records(domain)


def _run_async(coro):
    try:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        if loop.is_running():
            # Worker call-sites are sync; close coroutine to avoid warning and fallback to no-op.
            try:
                coro.close()
            except Exception:
                pass
            return []

        return loop.run_until_complete(coro)
    except Exception:
        return []


def _feed_provider() -> str:
    return os.getenv("FEED_PROVIDER", "pyth").strip().lower()


def _feed_kind() -> str:
    return os.getenv("FEED_KIND", "tick").strip().lower()


def _feed_granularity() -> str:
    return os.getenv("FEED_GRANULARITY", "1s").strip()


def _default_asset() -> str:
    assets_raw = os.getenv("FEED_ASSETS", "BTC")
    assets = [part.strip() for part in assets_raw.split(",") if part.strip()]
    return assets[0] if assets else "BTC"


def _candles_window_size() -> int:
    return int(os.getenv("FEED_CANDLES_WINDOW", "120"))


def _record_price(record) -> float | None:
    values = record.values or {}

    if "close" in values:
        try:
            return float(values.get("close"))
        except Exception:
            return None

    if "price" in values:
        try:
            return float(values.get("price"))
        except Exception:
            return None

    return None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
