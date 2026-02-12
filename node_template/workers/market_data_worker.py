from __future__ import annotations

import asyncio
import logging

from node_template.infrastructure.db import DBMarketRecordRepository, create_session
from node_template.services.market_data_service import MarketDataService, MarketDataSettings


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        force=True,
    )


def build_service() -> MarketDataService:
    settings = MarketDataSettings.from_env()
    session = create_session()
    return MarketDataService(
        settings=settings,
        market_record_repository=DBMarketRecordRepository(session),
    )


async def main() -> None:
    configure_logging()
    logging.getLogger(__name__).info("node_template market-data worker bootstrap")
    service = build_service()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
