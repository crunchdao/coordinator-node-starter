from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel, Field, Index, Column, JSON


class ModelRow(SQLModel, table=True):
    __tablename__ = "models"

    crunch_identifier: str = Field(primary_key=True)
    name: str
    deployment_identifier: str
    player_crunch_identifier: str
    player_name: str
    overall_score_recent: Optional[float] = None
    overall_score_steady: Optional[float] = None
    overall_score_anchor: Optional[float] = None

    scores_by_param: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )


class LeaderboardRow(SQLModel, table=True):
    __tablename__ = "leaderboards"

    id: str = Field(primary_key=True)
    created_at: datetime = Field(index=True)
    entries: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )


class PredictionRow(SQLModel, table=True):
    __tablename__ = "predictions"

    id: str = Field(primary_key=True)
    model_id: str = Field(index=True, foreign_key="models.crunch_identifier")
    asset: str = Field(index=True)
    horizon: int
    step: int
    status: str = Field(index=True)
    exec_time: float

    # JSON-serialized list[dict]
    distributions: Optional[list[dict]] = Field(
        default=None,
        sa_column=Column(JSON)
    )

    performed_at: datetime = Field(index=True)
    resolvable_at: datetime = Field(index=True)

    score_value: Optional[float] = None
    score_success: Optional[bool] = None
    score_failed_reason: Optional[str] = None
    score_scored_at: Optional[datetime] = Field(default=None, index=True)

    __table_args__ = (
        Index("idx_model_asset_horizon_step", "model_id", "asset", "horizon", "step"),
    )


class PredictionConfigRow(SQLModel, table=True):
    __tablename__ = "prediction_configs"

    id: str = Field(primary_key=True)
    asset: str = Field(index=True)
    horizon: int
    step: int
    prediction_interval: int
    active: bool = Field(index=True)
    order: int
