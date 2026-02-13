from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import SQLModel, delete

from coordinator_node.db.tables import PredictionConfigRow
from coordinator_node.schemas import ScheduledPredictionConfigEnvelope
from coordinator_node.db.session import create_session, engine

MINUTE = 60


def tables_to_reset() -> list[str]:
    return [
        "checkpoints",
        "snapshots",
        "scores",
        "predictions",
        "inputs",
        "leaderboards",
        "feed_records",
        "feed_ingestion_state",
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


def load_scheduled_prediction_configs() -> list[dict[str, Any]]:
    path = os.getenv("SCHEDULED_PREDICTION_CONFIGS_PATH")
    if not path:
        return default_scheduled_prediction_configs()

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("SCHEDULED_PREDICTION_CONFIGS_PATH must point to a JSON array")
    return payload


def migrate() -> None:
    """Create tables if they don't exist and upsert prediction configs.
    Safe to run on every boot — never drops data."""
    print("➡️  Creating tables (if not exist)...")
    SQLModel.metadata.create_all(engine)

    print("➡️  Upserting scheduled prediction configs...")
    with create_session() as session:
        session.exec(delete(PredictionConfigRow))
        for idx, config in enumerate(load_scheduled_prediction_configs(), start=1):
            envelope = ScheduledPredictionConfigEnvelope.model_validate(config)
            session.add(
                PredictionConfigRow(
                    id=f"CFG_{idx:03d}",
                    scope_key=envelope.scope_key,
                    scope_template_jsonb=envelope.scope_template,
                    schedule_jsonb=envelope.schedule.model_dump(),
                    active=envelope.active,
                    order=envelope.order,
                    meta_jsonb=envelope.meta,
                )
            )
        session.commit()

    print("✅ Database migration complete.")


def reset_db() -> None:
    """Drop all tables and recreate from scratch. Destroys all data."""
    print("⚠️  Dropping all tables...")
    with engine.begin() as conn:
        for table in tables_to_reset():
            conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))

    migrate()
    print("✅ Database reset complete.")


# Keep backward compat
init_db = reset_db


def auto_migrate() -> None:
    """Run migrate if tables don't exist yet. Called by workers on boot."""
    try:
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(engine)
        if not inspector.has_table("models"):
            migrate()
    except Exception:
        # First boot or connection issue — try migrate anyway
        try:
            migrate()
        except Exception:
            pass


if __name__ == "__main__":
    import sys
    if "--reset" in sys.argv:
        reset_db()
    else:
        migrate()
