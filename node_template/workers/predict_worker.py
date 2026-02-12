from __future__ import annotations

import asyncio
import logging

from node_template.config.runtime import RuntimeSettings
from node_template.contracts import CrunchContract
from node_template.infrastructure.db import DBModelRepository, DBPredictionRepository, create_session
from node_template.services.input_service import InputService
from node_template.services.realtime_predict_service import RealtimePredictService


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
        input_service=InputService.from_env(),
        contract=CrunchContract(),
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
