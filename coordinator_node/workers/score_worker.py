from __future__ import annotations

import asyncio
import logging

from coordinator_node.config.extensions import ExtensionSettings
from coordinator_node.config.runtime import RuntimeSettings
from coordinator_node.contracts import CrunchContract
from coordinator_node.extensions.callable_resolver import resolve_callable
from coordinator_node.db import (
    DBInputRepository,
    DBLeaderboardRepository,
    DBModelRepository,
    DBPredictionRepository,
    DBScoreRepository,
    DBSnapshotRepository,
    create_session,
)
from coordinator_node.services.feed_reader import FeedReader
from coordinator_node.services.score import ScoreService


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
        feed_reader=FeedReader.from_env(),
        input_repository=DBInputRepository(session),
        prediction_repository=DBPredictionRepository(session),
        score_repository=DBScoreRepository(session),
        snapshot_repository=DBSnapshotRepository(session),
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
