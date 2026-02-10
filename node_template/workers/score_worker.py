from __future__ import annotations

import argparse
import asyncio
import logging

from node_template.config.extensions import ExtensionSettings
from node_template.config.runtime import RuntimeSettings
from node_template.extensions.callable_resolver import resolve_callable
from node_template.services.score_service import ScoreService


def parse_arguments():
    parser = argparse.ArgumentParser(description="Node-template score worker")
    parser.add_argument("--prediction-id", required=False)
    return parser.parse_args()


def build_service() -> ScoreService:
    extension_settings = ExtensionSettings.from_env()
    runtime_settings = RuntimeSettings.from_env()

    scoring_function = resolve_callable(
        extension_settings.scoring_function,
        required_params=("prediction", "ground_truth"),
    )

    return ScoreService(
        checkpoint_interval_seconds=runtime_settings.checkpoint_interval_seconds,
        scoring_function=scoring_function,
    )


async def main(prediction_id: str | None = None) -> None:
    logging.getLogger(__name__).info("node_template score worker bootstrap")

    if prediction_id is not None:
        logging.getLogger(__name__).info("single prediction scoring not implemented yet")
        return

    service = build_service()
    await service.run()


if __name__ == "__main__":
    args = parse_arguments()
    asyncio.run(main(args.prediction_id))
