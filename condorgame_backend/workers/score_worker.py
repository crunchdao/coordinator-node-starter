import asyncio
import logging

from sqlmodel import Session

from condorgame_backend.infrastructure.db.init_db import engine
from condorgame_backend.infrastructure.db import DbModelRepository, DbPredictionRepository, DBLeaderboardRepository
from condorgame_backend.infrastructure.http import CrunchdaoPricesHttpRepository
from condorgame_backend.services.score_service import ScoreService
from condorgame_backend.utils.logging_config import setup_logging


def parse_arguments():
    import argparse
    parser = argparse.ArgumentParser(description="Score a specific prediction by ID for debugging or testing purposes.")
    parser.add_argument("--prediction-id", required=False, help="The ID of the prediction to score")
    return parser.parse_args()


async def main(prediction_id: str):
    setup_logging()
    logging.getLogger("condorgame_backend").setLevel(logging.DEBUG)

    session = Session(engine)

    model_repo = DbModelRepository(session)
    price_repo = CrunchdaoPricesHttpRepository()
    prediction_repo = DbPredictionRepository(session)

    leaderboard_repo = DBLeaderboardRepository(session)

    score_service = ScoreService(price_repo, model_repo, prediction_repo, leaderboard_repo)

    if prediction_id:
        prediction = score_service.score_prediction(prediction_repo.fetch_by_id(prediction_id))
        logging.info(f"Prediction {prediction_id} score: {prediction}")
        return

    await score_service.run()


if __name__ == "__main__":
    args = parse_arguments()
    asyncio.run(main(args.prediction_id))
