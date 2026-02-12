from __future__ import annotations

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
    DBScoreRepository,
    create_session,
)
from node_template.services.input_service import InputService
from node_template.services.score_service import ScoreService


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        force=True,
    )


def build_service() -> ScoreService:
    extension_settings = ExtensionSettings.from_env()
    runtime_settings = RuntimeSettings.from_env()

    scoring_function = resolve_callable(
        extension_settings.scoring_function,
        required_params=("prediction", "ground_truth"),
    )

    session = create_session()

    return ScoreService(
        checkpoint_interval_seconds=runtime_settings.checkpoint_interval_seconds,
        scoring_function=scoring_function,
        input_service=InputService.from_env(),
        prediction_repository=DBPredictionRepository(session),
        score_repository=DBScoreRepository(session),
        model_repository=DBModelRepository(session),
        leaderboard_repository=DBLeaderboardRepository(session),
        contract=CrunchContract(),
    )


async def main() -> None:
    configure_logging()
    logging.getLogger(__name__).info("score worker bootstrap")
    service = build_service()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
