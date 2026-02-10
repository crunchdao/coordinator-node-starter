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
        "scheduled_prediction_configs",
        "models",
    ]


def default_scheduled_prediction_configs() -> list[dict[str, Any]]:
    # Starter profile: generic scope + schedule for quick local end-to-end feedback.
    return [
        {
            "scope_key": "BTC-60-60",
            "scope_template": {"asset": "BTC", "horizon": 1 * MINUTE, "step": 1 * MINUTE},
            "schedule": {
                "prediction_interval_seconds": 1 * MINUTE,
                "resolve_after_seconds": 1 * MINUTE,
            },
            "active": True,
            "order": 1,
        },
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
        for idx, config in enumerate(default_scheduled_prediction_configs(), start=1):
            session.add(
                PredictionConfigRow(
                    id=f"CFG_{idx:03d}",
                    scope_key=config["scope_key"],
                    scope_template_jsonb=config["scope_template"],
                    schedule_jsonb=config["schedule"],
                    active=config["active"],
                    order=config["order"],
                    meta_jsonb={},
                )
            )
        session.commit()

    print("✅ Node-template database initialization complete.")


if __name__ == "__main__":
    init_db()
