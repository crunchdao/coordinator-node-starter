from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlmodel import SQLModel, delete

from coordinator_core.infrastructure.db.db_tables import PredictionConfigRow
from node_template.infrastructure.db.session import create_session, engine

MINUTE = 60


def tables_to_reset() -> list[str]:
    return [
        "emission_checkpoints",
        "checkpoints",
        "leaderboards",
        "model_scores",
        "predictions",
        "prediction_configs",
        "models",
    ]


def default_prediction_configs() -> list[dict[str, Any]]:
    # Starter profile: BTC-only, quick horizon for fast local end-to-end feedback.
    return [
        {"asset": "BTC", "horizon": 1 * MINUTE, "step": 1 * MINUTE, "prediction_interval": 1 * MINUTE, "active": True, "order": 1},
    ]


def init_db() -> None:
    print("➡️  Resetting canonical tables...")
    with engine.begin() as conn:
        for table in tables_to_reset():
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

    print("➡️  Creating coordinator core tables...")
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
