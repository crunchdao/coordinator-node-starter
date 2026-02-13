from __future__ import annotations

import asyncio
import logging

from coordinator.config.runtime import RuntimeSettings
from coordinator.contracts import CrunchContract
from coordinator.db import DBInputRepository, DBModelRepository, DBPredictionRepository, create_session
from coordinator.services.feed_reader import FeedReader
from coordinator.services.realtime_predict import RealtimePredictService


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        force=True,
    )


def build_service() -> RealtimePredictService:
    runtime_settings = RuntimeSettings.from_env()
    session = create_session()

    return RealtimePredictService(
        checkpoint_interval_seconds=runtime_settings.checkpoint_interval_seconds,
        feed_reader=FeedReader.from_env(),
        contract=CrunchContract(),
        input_repository=DBInputRepository(session),
        model_repository=DBModelRepository(session),
        prediction_repository=DBPredictionRepository(session),
        model_runner_node_host=runtime_settings.model_runner_node_host,
        model_runner_node_port=runtime_settings.model_runner_node_port,
        model_runner_timeout_seconds=runtime_settings.model_runner_timeout_seconds,
        crunch_id=runtime_settings.crunch_id,
        base_classname=runtime_settings.base_classname,
    )


async def main() -> None:
    configure_logging()
    logging.getLogger(__name__).info("predict worker bootstrap")
    service = build_service()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
