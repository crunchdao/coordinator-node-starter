import logging
from typing import Annotated, Generator, Any, List
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Depends, Query
from pydantic import BaseModel, Field

from sqlmodel import Session

from falcon2_backend.infrastructure.db import DbModelRepository, DBLeaderboardRepository
from falcon2_backend.infrastructure.db.init_db import engine, init_db
from falcon2_backend.services.interfaces.leaderboard_repository import LeaderboardRepository
from falcon2_backend.services.interfaces.model_repository import ModelRepository
from falcon2_backend.utils.logging_config import setup_logging

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


# ------------------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------------------

class LeaderboardEntryResponse(BaseModel):
    created_at: datetime
    model_id: int
    score_recent: float
    score_steady: float
    score_anchor: float
    rank: int


class GlobalMetricsResponse(BaseModel):
    model_id: int
    score_recent: float
    score_steady: float
    score_anchor: float


class ParamMetricsResponse(BaseModel):
    model_id: int
    param: str
    asset: str
    horizon: int
    step: int
    score_recent: float
    score_steady: float
    score_anchor: float


class MetricsReportArgs(BaseModel):
    model_ids: List[int] = Query(..., alias="projectIds")
    start: datetime
    end: datetime


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

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
            created_at=entry.created_at,
            model_id=entry.model_id,
            score_recent=entry.score.recent,
            score_steady=entry.score.steady,
            score_anchor=entry.score.anchor,
            rank=entry.rank,
        )
        for entry in entries_sorted
    ]


@app.get("/reports/models/global", response_model=List[GlobalMetricsResponse])
def get_models_global(
    filter_query: Annotated[MetricsReportArgs, Query()],
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
):
    """
    All models global metrics.
    (Filtering ignored for now — apply it when repository supports it)
    """
    models = model_repo.fetch_all()

    return [
        GlobalMetricsResponse(
            model_id=model.crunch_identifier,
            score_recent=model.overall_score.recent,
            score_steady=model.overall_score.steady,
            score_anchor=model.overall_score.anchor,
        )
        for _, model in models.items()
    ]


@app.get("/reports/models/params", response_model=List[ParamMetricsResponse])
def get_models_params(
    filter_query: Annotated[MetricsReportArgs, Query()],
    model_repo: Annotated[ModelRepository, Depends(get_model_repository)],
):
    """
    Detailed parameters metrics for each model.
    """
    models = model_repo.fetch_all()

    return [
        ParamMetricsResponse(
            model_id=model.crunch_identifier,
            param=f"{sbp.param.asset}-{sbp.param.horizon}-{sbp.param.step}",
            asset=sbp.param.asset,
            horizon=sbp.param.horizon,
            step=sbp.param.step,
            score_recent=sbp.score.recent,
            score_steady=sbp.score.steady,
            score_anchor=sbp.score.anchor,
        )
        for _, model in models.items()
        for sbp in model.scores_by_param
    ]


if __name__ == "__main__":
    setup_logging()
    logging.getLogger("falcon2_backend").setLevel(logging.DEBUG)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
    )