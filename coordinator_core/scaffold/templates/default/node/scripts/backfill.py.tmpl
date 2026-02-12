"""Manual historical backfill for market data feeds.

Usage:
    python scripts/backfill.py --provider binance --asset BTC --kind candle --granularity 1m \
        --from 2026-01-01 --to 2026-02-01

Or via make:
    make backfill FROM=2026-01-01 TO=2026-02-01
    make backfill FROM=2026-01-01 TO=2026-02-01 PROVIDER=binance ASSET=BTCUSDT KIND=candle GRANULARITY=1m
"""
import os
import sys

# Ensure app root is on sys.path when running as a script inside Docker
_app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from node_template.infrastructure.db import create_session
from node_template.infrastructure.db.market_records_repository import DBMarketRecordRepository
from node_template.services.backfill_service import BackfillService, BackfillRequest
from coordinator_runtime.data_feeds import create_default_registry


def parse_datetime(value):
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"Cannot parse datetime: {value!r} (expected YYYY-MM-DD or ISO format)")


def main():
    parser = argparse.ArgumentParser(description="Backfill market data from a feed provider")
    parser.add_argument("--provider", default=os.getenv("FEED_PROVIDER", "pyth"), help="Feed provider (default: $FEED_PROVIDER or pyth)")
    parser.add_argument("--asset", default=os.getenv("FEED_ASSETS", "BTC"), help="Asset symbol(s), comma-separated (default: $FEED_ASSETS or BTC)")
    parser.add_argument("--kind", default=os.getenv("FEED_KIND", "tick"), help="Data kind: tick or candle (default: $FEED_KIND or tick)")
    parser.add_argument("--granularity", default=os.getenv("FEED_GRANULARITY", "1s"), help="Granularity (default: $FEED_GRANULARITY or 1s)")
    parser.add_argument("--from", dest="start", required=True, type=parse_datetime, help="Start date (YYYY-MM-DD or ISO)")
    parser.add_argument("--to", dest="end", required=True, type=parse_datetime, help="End date (YYYY-MM-DD or ISO)")
    parser.add_argument("--page-size", type=int, default=500, help="Records per page (default: 500)")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        force=True,
    )
    logger = logging.getLogger("backfill")

    assets = tuple(a.strip() for a in args.asset.split(",") if a.strip())

    logger.info(
        "backfill starting provider=%s assets=%s kind=%s granularity=%s from=%s to=%s",
        args.provider, ",".join(assets), args.kind, args.granularity,
        args.start.isoformat(), args.end.isoformat(),
    )

    registry = create_default_registry()
    feed = registry.create_from_env(default_provider=args.provider)

    session = create_session()
    repo = DBMarketRecordRepository(session)

    request = BackfillRequest(
        provider=args.provider,
        assets=assets,
        kind=args.kind,
        granularity=args.granularity,
        start=args.start,
        end=args.end,
        page_size=args.page_size,
    )

    result = asyncio.run(BackfillService(feed=feed, repository=repo).run(request))

    logger.info(
        "backfill complete records_written=%d pages_fetched=%d",
        result.records_written, result.pages_fetched,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
