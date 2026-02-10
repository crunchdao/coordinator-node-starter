from __future__ import annotations

from typing import Any

from sqlmodel import SQLModel, delete

from coordinator_core.infrastructure.db.db_tables import PredictionConfigRow
from node_template.infrastructure.db.session import create_session, engine

HOUR = 60 * 60
MINUTE = 60
DAY = 24 * HOUR


def default_prediction_configs() -> list[dict[str, Any]]:
    return [
        {"asset": "BTC", "horizon": 1 * DAY, "step": 5 * MINUTE, "prediction_interval": 1 * HOUR, "active": True, "order": 1},
        {"asset": "BTC", "horizon": 1 * HOUR, "step": 1 * MINUTE, "prediction_interval": 12 * MINUTE, "active": True, "order": 2},
        {"asset": "ETH", "horizon": 1 * DAY, "step": 5 * MINUTE, "prediction_interval": 1 * HOUR, "active": True, "order": 3},
        {"asset": "ETH", "horizon": 1 * HOUR, "step": 1 * MINUTE, "prediction_interval": 12 * MINUTE, "active": True, "order": 4},
        {"asset": "XAU", "horizon": 1 * DAY, "step": 5 * MINUTE, "prediction_interval": 1 * HOUR, "active": True, "order": 5},
        {"asset": "XAU", "horizon": 1 * HOUR, "step": 1 * MINUTE, "prediction_interval": 12 * MINUTE, "active": True, "order": 6},
        {"asset": "SOL", "horizon": 1 * DAY, "step": 5 * MINUTE, "prediction_interval": 1 * HOUR, "active": True, "order": 7},
        {"asset": "SOL", "horizon": 1 * HOUR, "step": 1 * MINUTE, "prediction_interval": 12 * MINUTE, "active": True, "order": 8},
    ]


def init_db() -> None:
    print("➡️  Creating coordinator core tables if they do not exist...")
    SQLModel.metadata.create_all(engine)

    with create_session() as session:
        session.exec(delete(PredictionConfigRow))
        for idx, config in enumerate(default_prediction_configs(), start=1):
            session.add(
                PredictionConfigRow(
                    id=f"CFG_{idx:03d}",
                    asset=config["asset"],
                    horizon=config["horizon"],
                    step=config["step"],
                    prediction_interval=config["prediction_interval"],
                    active=config["active"],
                    order=config["order"],
                    meta_jsonb={},
                )
            )
        session.commit()

    print("✅ Node-template database initialization complete.")


if __name__ == "__main__":
    init_db()
