from __future__ import annotations

from datetime import datetime, timezone
import os
import unittest

from coordinator.entities.market_record import MarketIngestionState, MarketRecord
from coordinator.db.tables import MarketIngestionStateRow, MarketRecordRow
from coordinator.feeds.parquet_market_record_repository import ParquetMarketRecordRepository
from coordinator.config.runtime import RuntimeSettings
from coordinator.db.init_db import tables_to_reset
from coordinator.db.market_records import DBMarketRecordRepository


class TestMarketRecordStorage(unittest.TestCase):
    def test_market_record_tables_exist_with_expected_names(self):
        self.assertEqual(MarketRecordRow.__tablename__, "market_records")
        self.assertEqual(MarketIngestionStateRow.__tablename__, "market_ingestion_state")

    def test_market_record_table_has_required_fields(self):
        required_fields = {
            "id",
            "provider",
            "asset",
            "kind",
            "granularity",
            "ts_event",
            "ts_ingested",
            "values_jsonb",
            "meta_jsonb",
        }
        self.assertTrue(required_fields.issubset(MarketRecordRow.model_fields.keys()))

    def test_init_db_resets_market_storage_tables(self):
        tables = set(tables_to_reset())
        self.assertIn("market_records", tables)
        self.assertIn("market_ingestion_state", tables)

    def test_runtime_defaults_include_feed_provider_and_market_ttl(self):
        settings = RuntimeSettings.from_env()
        self.assertEqual(settings.feed_provider, "pyth")
        self.assertEqual(settings.market_record_ttl_days, 90)

    def test_runtime_allows_feed_provider_and_ttl_override(self):
        previous_provider = os.environ.get("FEED_PROVIDER")
        previous_ttl = os.environ.get("MARKET_RECORD_TTL_DAYS")
        os.environ["FEED_PROVIDER"] = "binance"
        os.environ["MARKET_RECORD_TTL_DAYS"] = "120"
        try:
            settings = RuntimeSettings.from_env()
            self.assertEqual(settings.feed_provider, "binance")
            self.assertEqual(settings.market_record_ttl_days, 120)
        finally:
            if previous_provider is None:
                os.environ.pop("FEED_PROVIDER", None)
            else:
                os.environ["FEED_PROVIDER"] = previous_provider

            if previous_ttl is None:
                os.environ.pop("MARKET_RECORD_TTL_DAYS", None)
            else:
                os.environ["MARKET_RECORD_TTL_DAYS"] = previous_ttl

    def test_db_market_repository_row_mapping_roundtrip(self):
        record = MarketRecord(
            provider="pyth",
            asset="BTCUSD",
            kind="tick",
            granularity="1s",
            ts_event=datetime(2026, 1, 1, tzinfo=timezone.utc),
            values={"price": 50000.0},
            meta={"source": "hermes"},
        )

        row = DBMarketRecordRepository._domain_to_row(record)
        hydrated = DBMarketRecordRepository._row_to_domain(row)

        self.assertEqual(hydrated.provider, "pyth")
        self.assertEqual(hydrated.asset, "BTCUSD")
        self.assertEqual(hydrated.values["price"], 50000.0)

    def test_db_market_repository_exposes_feed_summary_and_tail_methods(self):
        self.assertTrue(callable(getattr(DBMarketRecordRepository, "list_indexed_feeds")))
        self.assertTrue(callable(getattr(DBMarketRecordRepository, "tail_records")))
        self.assertTrue(callable(getattr(DBMarketRecordRepository, "fetch_latest_record")))

    def test_parquet_repository_exists_as_stub_for_future_cold_storage(self):
        repo = ParquetMarketRecordRepository(root_path="/tmp/market-records")

        record = MarketRecord(
            provider="pyth",
            asset="BTCUSD",
            kind="tick",
            granularity="1s",
            ts_event=datetime(2026, 1, 1, tzinfo=timezone.utc),
            values={"price": 50000.0},
            meta={},
        )

        with self.assertRaises(NotImplementedError):
            repo.append_records([record])

        state = MarketIngestionState(
            provider="pyth",
            asset="BTCUSD",
            kind="tick",
            granularity="1s",
            last_event_ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
            meta={},
        )
        with self.assertRaises(NotImplementedError):
            repo.set_watermark(state)


if __name__ == "__main__":
    unittest.main()
