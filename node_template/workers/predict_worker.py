from __future__ import annotations

import asyncio
import logging

from node_template.config.extensions import ExtensionSettings
from node_template.config.runtime import RuntimeSettings
from node_template.extensions.callable_resolver import resolve_callable
from node_template.infrastructure.db import DBModelRepository, DBPredictionRepository, create_session
from node_template.services.predict_service import PredictService


def build_service() -> PredictService:
    extension_settings = ExtensionSettings.from_env()
    runtime_settings = RuntimeSettings.from_env()

    inference_input_builder = resolve_callable(
        extension_settings.inference_input_builder,
        required_params=("raw_input",),
    )

    session = create_session()

    return PredictService(
        checkpoint_interval_seconds=runtime_settings.checkpoint_interval_seconds,
        inference_input_builder=inference_input_builder,
        model_repository=DBModelRepository(session),
        prediction_repository=DBPredictionRepository(session),
        model_runner_node_host=runtime_settings.model_runner_node_host,
        model_runner_node_port=runtime_settings.model_runner_node_port,
        model_runner_timeout_seconds=runtime_settings.model_runner_timeout_seconds,
        crunch_id=runtime_settings.crunch_id,
        base_classname=runtime_settings.base_classname,
    )


async def main() -> None:
    logging.getLogger(__name__).info("node_template predict worker bootstrap")
    service = build_service()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
