from __future__ import annotations

import argparse
import asyncio
import logging

from node_template.config.extensions import ExtensionSettings
from node_template.config.runtime import RuntimeSettings
from node_template.contracts import CrunchContract
from node_template.extensions.callable_resolver import resolve_callable
from node_template.infrastructure.db import (
    DBLeaderboardRepository,
    DBModelRepository,
    DBPredictionRepository,
    create_session,
)
from node_template.services.score_service import ScoreService


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        force=True,
    )


def parse_arguments():
    parser = argparse.ArgumentParser(description="Node-template score worker")
    parser.add_argument("--prediction-id", required=False)
    return parser.parse_args()


def build_service() -> ScoreService:
    extension_settings = ExtensionSettings.from_env()
    runtime_settings = RuntimeSettings.from_env()
    contract = CrunchContract()

    scoring_function = resolve_callable(
        extension_settings.scoring_function,
        required_params=("prediction", "ground_truth"),
    )
    ground_truth_resolver = resolve_callable(
        extension_settings.ground_truth_resolver,
        required_params=("prediction",),
    )

    session = create_session()

    return ScoreService(
        checkpoint_interval_seconds=runtime_settings.checkpoint_interval_seconds,
        scoring_function=scoring_function,
        prediction_repository=DBPredictionRepository(session),
        model_repository=DBModelRepository(session),
        leaderboard_repository=DBLeaderboardRepository(session),
        ground_truth_resolver=ground_truth_resolver,
        contract=contract,
    )


async def main(prediction_id: str | None = None) -> None:
    configure_logging()
    logging.getLogger(__name__).info("node_template score worker bootstrap")

    if prediction_id is not None:
        logging.getLogger(__name__).info("single prediction scoring not implemented yet")
        return

    service = build_service()
    await service.run()


if __name__ == "__main__":
    args = parse_arguments()
    asyncio.run(main(args.prediction_id))
