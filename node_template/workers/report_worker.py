from __future__ import annotations

import logging
from typing import Annotated, Any, Generator

import uvicorn
from fastapi import Depends, FastAPI
from sqlmodel import Session

from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from node_template.infrastructure.db import DBLeaderboardRepository, DBModelRepository, create_session

app = FastAPI(title="Node Template Report Worker")


def get_db_session() -> Generator[Session, Any, None]:
    with create_session() as session:
        yield session


def get_model_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> ModelRepository:
    return DBModelRepository(session_db)


def get_leaderboard_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> LeaderboardRepository:
    return DBLeaderboardRepository(session_db)


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/reports/models")
def get_models(
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)]
) -> list[dict]:
    models = model_repo.fetch_all()

    return [
        {
            "model_id": model.id,
            "model_name": model.name,
            "cruncher_name": model.player_name,
            "cruncher_id": model.player_id,
            "deployment_id": model.deployment_identifier,
        }
        for model in models.values()
    ]


@app.get("/reports/leaderboard")
def get_leaderboard(
    leaderboard_repo: Annotated[LeaderboardRepository, Depends(get_leaderboard_repository)]
) -> list[dict]:
    leaderboard = leaderboard_repo.get_latest()
    if leaderboard is None:
        return []

    created_at = leaderboard.get("created_at")
    entries = leaderboard.get("entries", [])

    normalized_entries = []
    for entry in entries:
        score_obj = entry.get("score", {}) if isinstance(entry.get("score"), dict) else {}

        normalized_entries.append(
            {
                "created_at": created_at,
                "model_id": entry.get("model_id"),
                "score_recent": entry.get("score_recent", score_obj.get("recent")),
                "score_steady": entry.get("score_steady", score_obj.get("steady")),
                "score_anchor": entry.get("score_anchor", score_obj.get("anchor")),
                "rank": entry.get("rank", 999999),
                "model_name": entry.get("model_name"),
                "cruncher_name": entry.get("cruncher_name", entry.get("player_name")),
            }
        )

    return sorted(normalized_entries, key=lambda item: item.get("rank", 999999))


if __name__ == "__main__":
    logging.getLogger(__name__).info("node_template report worker bootstrap")
    uvicorn.run(app, host="0.0.0.0", port=8000)
