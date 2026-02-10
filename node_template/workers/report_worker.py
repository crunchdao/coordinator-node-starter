from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any, Generator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlmodel import Session

from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from coordinator_core.services.interfaces.prediction_repository import PredictionRepository
from node_template.infrastructure.db import (
    DBLeaderboardRepository,
    DBModelRepository,
    DBPredictionRepository,
    create_session,
)

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


def get_prediction_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> PredictionRepository:
    return DBPredictionRepository(session_db)


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


@app.get("/reports/models/global")
def get_models_global(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    rows: list[dict] = []
    for model_id, predictions in predictions_by_model.items():
        scores = [p.score.value for p in predictions if p.score and p.score.success and p.score.value is not None]
        if not scores:
            continue

        avg = float(sum(scores) / len(scores))
        performed_at = max((p.performed_at for p in predictions), default=end)

        rows.append(
            {
                "model_id": model_id,
                "score_recent": avg,
                "score_steady": avg,
                "score_anchor": avg,
                "performed_at": performed_at,
            }
        )

    return rows


@app.get("/reports/models/params")
def get_models_params(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    grouped: dict[tuple[str, str, int, int], list] = {}
    for model_id, predictions in predictions_by_model.items():
        for prediction in predictions:
            key = (model_id, prediction.asset, prediction.horizon, prediction.step)
            grouped.setdefault(key, []).append(prediction)

    rows: list[dict] = []
    for (model_id, asset, horizon, step), predictions in grouped.items():
        scores = [p.score.value for p in predictions if p.score and p.score.success and p.score.value is not None]
        if not scores:
            continue

        avg = float(sum(scores) / len(scores))
        performed_at = max((p.performed_at for p in predictions), default=end)

        rows.append(
            {
                "model_id": model_id,
                "param": f"{asset}-{horizon}-{step}",
                "asset": asset,
                "horizon": horizon,
                "step": step,
                "score_recent": avg,
                "score_steady": avg,
                "score_anchor": avg,
                "performed_at": performed_at,
            }
        )

    return rows


@app.get("/reports/predictions")
def get_predictions(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[PredictionRepository, Depends(get_prediction_repository)],
) -> list[dict]:
    if len(model_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service is available only for one model at a time. Please provide a single model_id.",
        )

    predictions_by_model = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    rows: list[dict] = []
    for _, predictions in predictions_by_model.items():
        for prediction in predictions:
            score = prediction.score
            rows.append(
                {
                    "model_id": prediction.model_id,
                    "param": f"{prediction.asset}-{prediction.horizon}-{prediction.step}",
                    "asset": prediction.asset,
                    "horizon": prediction.horizon,
                    "step": prediction.step,
                    "score_value": score.value if score else None,
                    "score_failed": (not score.success) if score else True,
                    "score_failed_reason": score.failed_reason if score else "Prediction not scored",
                    "scored_at": score.scored_at if score else None,
                    "performed_at": prediction.performed_at,
                }
            )

    return sorted(rows, key=lambda row: row["performed_at"])


if __name__ == "__main__":
    logging.getLogger(__name__).info("node_template report worker bootstrap")
    uvicorn.run(app, host="0.0.0.0", port=8000)
