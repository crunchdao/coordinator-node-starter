"""Tests for the backfill script and service."""
from __future__ import annotations

import asyncio
import py_compile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from coordinator.feeds.contracts import FeedDataRecord, FeedFetchRequest


class TestBackfillService(unittest.TestCase):
    """Unit tests for the backfill runner logic."""

    def _make_records(self, subject: str, base_ts: int, count: int) -> list[FeedDataRecord]:
        return [
            FeedDataRecord(
                source="binance",
                subject=subject,
                kind="candle",
                granularity="1m",
                ts_event=base_ts + i * 60,
                values={"open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
            )
            for i in range(count)
        ]

    def test_backfill_paginates_through_time_range(self):
        from coordinator.services.backfill import BackfillService, BackfillRequest

        repo = MagicMock()
        repo.append_records = MagicMock(return_value=5)
        repo.set_watermark = MagicMock()

        feed = AsyncMock()
        feed.fetch = AsyncMock(side_effect=[self._make_records("BTC", 1707700000, 5), []])

        request = BackfillRequest(
            source="binance",
            subjects=("BTC",),
            kind="candle",
            granularity="1m",
            start=datetime(2026, 2, 1, tzinfo=timezone.utc),
            end=datetime(2026, 2, 1, 0, 5, tzinfo=timezone.utc),
            page_size=500,
        )

        service = BackfillService(feed=feed, repository=repo)
        result = asyncio.run(service.run(request))

        self.assertEqual(result.records_written, 5)
        self.assertGreaterEqual(feed.fetch.call_count, 1)
        repo.append_records.assert_called()

    def test_backfill_returns_zero_when_no_data(self):
        from coordinator.services.backfill import BackfillService, BackfillRequest

        repo = MagicMock()
        repo.append_records = MagicMock(return_value=0)

        feed = AsyncMock()
        feed.fetch = AsyncMock(return_value=[])

        request = BackfillRequest(
            source="binance",
            subjects=("BTC",),
            kind="candle",
            granularity="1m",
            start=datetime(2026, 2, 1, tzinfo=timezone.utc),
            end=datetime(2026, 2, 1, 0, 5, tzinfo=timezone.utc),
        )

        service = BackfillService(feed=feed, repository=repo)
        result = asyncio.run(service.run(request))

        self.assertEqual(result.records_written, 0)

    def test_backfill_advances_start_past_last_record(self):
        from coordinator.services.backfill import BackfillService, BackfillRequest

        repo = MagicMock()
        repo.append_records = MagicMock(return_value=3)
        repo.set_watermark = MagicMock()

        feed = AsyncMock()
        feed.fetch = AsyncMock(side_effect=[self._make_records("BTC", 1000, 3), []])

        request = BackfillRequest(
            source="binance",
            subjects=("BTC",),
            kind="candle",
            granularity="1m",
            start=datetime(1970, 1, 1, 0, 16, 40, tzinfo=timezone.utc),
            end=datetime(1970, 1, 1, 0, 25, tzinfo=timezone.utc),
        )

        service = BackfillService(feed=feed, repository=repo)
        asyncio.run(service.run(request))

        second_call = feed.fetch.call_args_list[1]
        req: FeedFetchRequest = second_call[0][0]
        self.assertGreater(req.start_ts, 1000)


class TestBackfillScaffold(unittest.TestCase):
    def test_scaffold_generates_backfill_script(self):
        from tests.test_coordinator_cli_init import _cwd, main

        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                script = Path("btc-trader/crunch-node-btc-trader/scripts/backfill.py")
                self.assertTrue(script.exists(), f"backfill script not found at {script}")
                py_compile.compile(str(script), doraise=True)

                content = script.read_text(encoding="utf-8")
                self.assertIn("--from", content)
                self.assertIn("--to", content)
                self.assertIn("--source", content)

    def test_scaffold_makefile_has_backfill_target(self):
        from tests.test_coordinator_cli_init import _cwd, main

        with tempfile.TemporaryDirectory() as tmp:
            with _cwd(Path(tmp)):
                code = main(["init", "btc-trader"])
                self.assertEqual(code, 0)

                makefile = Path("btc-trader/crunch-node-btc-trader/Makefile").read_text(encoding="utf-8")
                self.assertIn("backfill", makefile)


if __name__ == "__main__":
    unittest.main()
