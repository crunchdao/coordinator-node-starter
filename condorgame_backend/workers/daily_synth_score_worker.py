import asyncio
import logging
from datetime import date

from sqlmodel import Session

from condorgame_backend.infrastructure.db.init_db import engine
from condorgame_backend.infrastructure.db import DbModelRepository, DbPredictionRepository, DBLeaderboardRepository, DBDailySynthLeaderboardRepository
from condorgame_backend.infrastructure.http import CrunchdaoPricesHttpRepository
from condorgame_backend.services.daily_synth_score_service import DailySynthScoreService
from condorgame_backend.utils.logging_config import setup_logging


# def parse_arguments():
#     import argparse
#     parser = argparse.ArgumentParser(description="Compute leaderboard for a specific day using synth scoring.")
#     parser.add_argument("--day", required=True, help="YYYY-MM-DD")
#     return parser.parse_args()

def parse_arguments():
    import argparse
    parser = argparse.ArgumentParser(description="Score a specific prediction by ID for debugging or testing purposes.")
    parser.add_argument("--prediction-id", required=False, help="The ID of the prediction to score")
    return parser.parse_args()


# async def main(day: str):
#     setup_logging()
#     logging.getLogger("condorgame_backend").setLevel(logging.DEBUG)

#     session = Session(engine)

#     model_repo = DbModelRepository(session)
#     price_repo = CrunchdaoPricesHttpRepository()
#     prediction_repo = DbPredictionRepository(session)

#     daily_synth_leaderboard_repo = DBLeaderboardRepository(session)

#     daily_synth_score_service = DailySynthScoreService(price_repo, model_repo, prediction_repo, daily_synth_leaderboard_repo)

#     if day:
#         day = date.fromisoformat(day)

#         try:
#             with Session(engine) as session:
#                 daily_synth_score_service.run_for_day(session, day)
#         except Exception:
#             logging.exception(f"Failed to compute daily synth leaderboard for date: {day}")


async def main(prediction_id: str):
    setup_logging()
    logging.getLogger("condorgame_backend").setLevel(logging.DEBUG)

    session = Session(engine)

    model_repo = DbModelRepository(session)
    price_repo = CrunchdaoPricesHttpRepository()
    prediction_repo = DbPredictionRepository(session)

    daily_synth_leaderboard_repo = DBDailySynthLeaderboardRepository(session)

    score_service = DailySynthScoreService(price_repo, model_repo, prediction_repo, daily_synth_leaderboard_repo)

    if prediction_id:
        prediction = score_service.score_prediction(prediction_repo.fetch_by_id(prediction_id))
        logging.info(f"Prediction {prediction_id} score: {prediction}")
        return

    await score_service.run()

if __name__ == "__main__":
    args = parse_arguments()
    # asyncio.run(main(args.day))
    asyncio.run(main(args.prediction_id))
