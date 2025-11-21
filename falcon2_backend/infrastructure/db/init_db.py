from sqlmodel import SQLModel, create_engine, Session

from . import DbPredictionRepository
from .db_tables import ModelRow, LeaderboardRow, PredictionRow, PredictionConfigRow
from ...entities.prediction import PredictionConfig, PredictionParams

import os

DATABASE_URL = f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@" \
               f"{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

engine = create_engine(DATABASE_URL)

HOUR = 60 * 60
MINUTE = 60
DAY = 24 * HOUR


def default_prediction_config():
    return [
        PredictionConfig(PredictionParams('BTC', 1 * DAY, 5 * MINUTE), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams('BTC', 1 * HOUR, 1 * MINUTE), 12 * MINUTE, True, 2),

        PredictionConfig(PredictionParams('ETH', 1 * DAY, 5 * MINUTE), 1 * HOUR, True, 3),
        PredictionConfig(PredictionParams('ETH', 1 * HOUR, 1 * MINUTE), 12 * MINUTE, True, 4),

        PredictionConfig(PredictionParams('XAU', 1 * DAY, 5 * MINUTE), 1 * HOUR, True, 5),
        PredictionConfig(PredictionParams('XAU', 1 * HOUR, 1 * MINUTE), 12 * MINUTE, True, 6),

        PredictionConfig(PredictionParams('SOL', 1 * DAY, 5 * MINUTE), 1 * HOUR, True, 7),
        PredictionConfig(PredictionParams('SOL', 1 * HOUR, 1 * MINUTE), 12 * MINUTE, True, 8),
    ]


def init_db() -> None:
    print("➡️  Creating tables if they do not exist...")
    SQLModel.metadata.create_all(engine)
    print("✅ Database initialization complete.")

    session = Session(engine)
    prediction_repo = DbPredictionRepository(session)

    # todo improve the update
    prediction_repo.delete_configs()
    prediction_repo.save_all_configs(default_prediction_config())


if __name__ == "__main__":
    init_db()
