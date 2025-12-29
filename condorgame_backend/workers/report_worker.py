import logging
from typing import Annotated, Generator, Any, List, Optional
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Depends, Query, HTTPException, status
from pydantic import BaseModel, Field

from sqlmodel import Session

from condorgame_backend.infrastructure.db import DbModelRepository, DBLeaderboardRepository, DbPredictionRepository
from condorgame_backend.infrastructure.db.init_db import engine, init_db
from condorgame_backend.services.interfaces.leaderboard_repository import LeaderboardRepository
from condorgame_backend.services.interfaces.model_repository import ModelRepository
from condorgame_backend.services.interfaces.prediction_repository import PredictionRepository
from condorgame_backend.utils.logging_config import setup_logging

# ------------------------------------------------------------------------------
# FastAPI App
# ------------------------------------------------------------------------------

app = FastAPI()


# ------------------------------------------------------------------------------
# DB Session Dependency (SQLModel)
# ------------------------------------------------------------------------------

def get_db_session() -> Generator[Session, Any, None]:
    with Session(engine) as session:
        yield session


def get_model_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> ModelRepository:
    return DbModelRepository(session_db)


def get_leaderboard_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> LeaderboardRepository:
    return DBLeaderboardRepository(session_db)


def get_prediction_repository(
    session_db: Annotated[Session, Depends(get_db_session)]
) -> DbPredictionRepository:
    return DbPredictionRepository(session_db)


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------

class ModelEntryReponse(BaseModel):
    model_id: str
    model_name: str
    cruncher_name: str
    cruncher_id: str
    deployment_identifier: str


class LeaderboardEntryResponse(BaseModel):
    created_at: datetime
    model_id: str
    score_recent: Optional[float]
    score_steady: Optional[float]
    score_anchor: Optional[float]
    rank: int
    model_name: str
    cruncher_name: str


class GlobalMetricsResponse(BaseModel):
    model_id: str
    score_recent: Optional[float]
    score_steady: Optional[float]
    score_anchor: Optional[float]
    performed_at: datetime


class ParamMetricsResponse(BaseModel):
    model_id: str
    param: str
    asset: str
    horizon: int
    step: int
    score_recent: Optional[float]
    score_steady: Optional[float]
    score_anchor: Optional[float]
    performed_at: datetime


class PredictionScoreResponse(BaseModel):
    model_id: str
    param: str
    asset: str
    horizon: int
    step: int
    score_value: Optional[float]
    score_failed: bool
    score_failed_reason: Optional[str]
    scored_at: datetime
    performed_at: datetime


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.get("/reports/models", response_model=List[ModelEntryReponse])
def get_models(
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)]
) -> List[ModelEntryReponse]:
    """
    Fetch and return a list of all available models.
    """
    models = model_repo.fetch_all()

    return [
        ModelEntryReponse(
            model_id=model.crunch_identifier,
            model_name=model.name,
            cruncher_name=model.player.name,
            cruncher_id=model.player.crunch_identifier,
            deployment_identifier=model.deployment_identifier,
        )
        for model in models.values()
    ]


@app.get("/reports/leaderboard", response_model=List[LeaderboardEntryResponse])
def get_leaderboard(
    leaderboard_repo: Annotated[
        LeaderboardRepository, Depends(get_leaderboard_repository)
    ]
):
    leaderboard = leaderboard_repo.get_latest()
    if leaderboard is None:
        return []

    entries_sorted = sorted(leaderboard.entries, key=lambda x: x.rank)

    return [
        LeaderboardEntryResponse(
            created_at=leaderboard.created_at,
            model_id=entry.model_id,
            score_recent=entry.score.recent,
            score_steady=entry.score.steady,
            score_anchor=entry.score.anchor,
            rank=entry.rank,
            model_name=entry.model_name,
            cruncher_name=entry.player_name
        )
        for entry in entries_sorted
    ]


@app.get("/reports/models/global", response_model=List[GlobalMetricsResponse])
def get_models_global(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
):
    """
    All models global metrics.
    (Filtering ignored for now — apply it when repository supports it)
    """
    model_score_snapshots = model_repo.fetch_model_score_snapshots(model_ids=model_ids, _from=start, to=end)

    return [
        GlobalMetricsResponse(
            model_id=score_snapshot.model_id,
            score_recent=score_snapshot.overall_score.recent,
            score_steady=score_snapshot.overall_score.steady,
            score_anchor=score_snapshot.overall_score.anchor,
            performed_at=score_snapshot.performed_at
        )
        for _, score_snapshots in model_score_snapshots.items()
        for score_snapshot in score_snapshots
    ]


@app.get("/reports/models/params", response_model=List[ParamMetricsResponse])
def get_models_params(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
):
    """
    Detailed parameters metrics for each model.
    """
    model_score_snapshots = model_repo.fetch_model_score_snapshots(model_ids=model_ids, _from=start, to=end)

    return [
        ParamMetricsResponse(
            model_id=score_snapshot.model_id,
            param=f"{sbp.param.asset}-{sbp.param.horizon}-{sbp.param.step}",
            asset=sbp.param.asset,
            horizon=sbp.param.horizon,
            step=sbp.param.step,
            score_recent=sbp.score.recent,
            score_steady=sbp.score.steady,
            score_anchor=sbp.score.anchor,
            performed_at=score_snapshot.performed_at
        )
        for _, score_snapshots in model_score_snapshots.items()
        for score_snapshot in score_snapshots
        for sbp in score_snapshot.scores_by_param
    ]


@app.get("/reports/predictions", response_model=List[PredictionScoreResponse])
def get_models_params(
    model_ids: Annotated[list[str], Query(..., alias="projectIds")],
    start: Annotated[datetime, Query(...)],
    end: Annotated[datetime, Query(...)],
    prediction_repo: Annotated[
        PredictionRepository,
        Depends(get_prediction_repository)
    ],
):
    """
    Detailed parameters metrics for each model.
    """

    if len(model_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service is available only for one model at a time. Please provide a single model_id."
        )

    predictions_scored = prediction_repo.query_scores(model_ids=model_ids, _from=start, to=end)

    return [
        PredictionScoreResponse(
            model_id=prediction.model_id,
            param=f"{prediction.asset}-{prediction.horizon}-{prediction.step}",
            asset=prediction.asset,
            horizon=prediction.horizon,
            step=prediction.step,
            score_value=prediction.score_value,
            score_failed=not prediction.score_success,
            score_failed_reason=prediction.score_failed_reason,
            scored_at=prediction.score_scored_at,
            performed_at=prediction.performed_at,
        )
        for _, predictions in predictions_scored.items()
        for prediction in predictions
    ]


if __name__ == "__main__":
    setup_logging()
    logging.getLogger("condorgame_backend").setLevel(logging.DEBUG)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )
