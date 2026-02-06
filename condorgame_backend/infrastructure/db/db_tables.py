from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlmodel import SQLModel, Field, Index, Column, JSON, ARRAY, Integer


class ModelRow(SQLModel, table=True):
    __tablename__ = "models"

    crunch_identifier: str = Field(primary_key=True)
    name: str
    deployment_identifier: str
    player_crunch_identifier: str
    player_name: str
    runner_id: str
    overall_score_recent: Optional[float] = None
    overall_score_steady: Optional[float] = None
    overall_score_anchor: Optional[float] = None

    scores_by_param: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )


class ModelScoreSnapshotRow(SQLModel, table=True):
    __tablename__ = "model_score_snapshots"

    id: str = Field(primary_key=True)

    overall_score_recent: Optional[float] = None
    overall_score_steady: Optional[float] = None
    overall_score_anchor: Optional[float] = None

    scores_by_param: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )
    model_id: str = Field(index=True, foreign_key="models.crunch_identifier")
    performed_at: datetime = Field(index=True)


class LeaderboardRow(SQLModel, table=True):
    __tablename__ = "leaderboards"

    id: str = Field(primary_key=True)
    created_at: datetime = Field(index=True)
    entries: list[dict] = Field(
        default_factory=list,
        sa_column=Column(JSON)
    )


class DailySynthLeaderboardRow(SQLModel, table=True):
    __tablename__ = "daily_synth_leaderboards"

    id: str = Field(primary_key=True)
    created_at: datetime = Field(index=True)
    day: date = Field(index=True)
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
    steps: tuple[int,...] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(Integer), nullable=False),
    )
    status: str = Field(index=True)
    exec_time: float

    # JSON-serialized list[dict]
    distributions: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON)
    )

    performed_at: datetime = Field(index=True)
    resolvable_at: datetime = Field(index=True)

    score_raw_value: Optional[float] = None
    score_final_value: Optional[float] = None
    score_success: Optional[bool] = None
    score_failed_reason: Optional[str] = None
    score_scored_at: Optional[datetime] = Field(default=None, index=True)

    __table_args__ = (
        Index("idx_model_asset_horizon_steps", "model_id", "asset", "horizon", "steps"),
    )


class PredictionConfigRow(SQLModel, table=True):
    __tablename__ = "prediction_configs"

    id: str = Field(primary_key=True)
    asset: str = Field(index=True)
    horizon: int
    steps: tuple[int,...] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(Integer), nullable=False),
    )
    prediction_interval: int
    active: bool = Field(index=True)
    order: int
