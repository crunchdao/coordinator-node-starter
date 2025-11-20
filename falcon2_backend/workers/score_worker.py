import asyncio
import logging

from sqlmodel import Session

from falcon2_backend.infrastructure.db.init_db import engine
from falcon2_backend.infrastructure.db import DbModelRepository, DbPredictionRepository, DBLeaderboardRepository
from falcon2_backend.infrastructure.http.prices_http_repository import PythPriceHttpRepository
from falcon2_backend.services.score_service import ScoreService
from falcon2_backend.utils.logging_config import setup_logging


async def main():
    setup_logging()
    logging.getLogger("falcon2_backend").setLevel(logging.DEBUG)

    session = Session(engine)

    model_repo = DbModelRepository(session)
    price_repo = PythPriceHttpRepository()
    prediction_repo = DbPredictionRepository(session)

    leaderboard_repo = DBLeaderboardRepository(session)

    score_service = ScoreService(price_repo, model_repo, prediction_repo, leaderboard_repo)
    await score_service.run()


if __name__ == "__main__":
    asyncio.run(main())
