import asyncio
import logging

from sqlmodel import Session

from condorgame_backend.infrastructure.db.init_db import engine
from condorgame_backend.infrastructure.http import CrunchdaoPricesHttpRepository
from condorgame_backend.services.predict_service import PredictService
from condorgame_backend.infrastructure.db import DbModelRepository, DbPredictionRepository
from condorgame_backend.utils.logging_config import setup_logging


async def main():
    setup_logging()
    logging.getLogger("condorgame_backend").setLevel(logging.DEBUG)

    session = Session(engine)

    model_repo = DbModelRepository(session)
    price_repo = CrunchdaoPricesHttpRepository()
    prediction_repo = DbPredictionRepository(session)

    predict_service = PredictService(price_repo, model_repo, prediction_repo)
    await predict_service.run()


if __name__ == "__main__":
    asyncio.run(main())
