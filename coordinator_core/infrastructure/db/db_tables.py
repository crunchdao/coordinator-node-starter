from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelRow(SQLModel, table=True):
    __tablename__ = "models"

    id: str = Field(primary_key=True)
    name: str
    deployment_identifier: str
    player_id: str = Field(index=True)
    player_name: str

    overall_score_recent: Optional[float] = None
    overall_score_steady: Optional[float] = None
    overall_score_anchor: Optional[float] = None

    scores_by_param_jsonb: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class PredictionRow(SQLModel, table=True):
    __tablename__ = "predictions"

    id: str = Field(primary_key=True)
    model_id: str = Field(index=True, foreign_key="models.id")

    asset: str = Field(index=True)
    horizon: int
    step: int

    status: str = Field(index=True)
    exec_time_ms: float

    inference_input_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )
    inference_output_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    performed_at: datetime = Field(default_factory=utc_now, index=True)
    resolvable_at: datetime = Field(index=True)

    score_value: Optional[float] = None
    score_success: Optional[bool] = None
    score_failed_reason: Optional[str] = None
    score_scored_at: Optional[datetime] = Field(default=None, index=True)

    __table_args__ = (
        Index("idx_predictions_lookup", "model_id", "asset", "horizon", "step"),
    )


class ModelScoreRow(SQLModel, table=True):
    __tablename__ = "model_scores"

    id: str = Field(primary_key=True)
    model_id: str = Field(index=True, foreign_key="models.id")

    recent: Optional[float] = None
    steady: Optional[float] = None
    anchor: Optional[float] = None

    score_payload_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    computed_at: datetime = Field(default_factory=utc_now, index=True)


class LeaderboardRow(SQLModel, table=True):
    __tablename__ = "leaderboards"

    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=utc_now, index=True)

    entries_jsonb: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )


class CheckpointRow(SQLModel, table=True):
    __tablename__ = "checkpoints"

    id: str = Field(primary_key=True)
    checkpoint_kind: str = Field(index=True)
    interval_seconds: int

    last_run_at: Optional[datetime] = Field(default=None, index=True)
    next_run_at: Optional[datetime] = Field(default=None, index=True)

    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )


class EmissionCheckpointRow(SQLModel, table=True):
    __tablename__ = "emission_checkpoints"

    id: str = Field(primary_key=True)
    checkpoint_id: str = Field(index=True, foreign_key="checkpoints.id")
    emitted_at: datetime = Field(default_factory=utc_now, index=True)

    payload_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )


class PredictionConfigRow(SQLModel, table=True):
    __tablename__ = "prediction_configs"

    id: str = Field(primary_key=True)

    asset: str = Field(index=True)
    horizon: int
    step: int
    prediction_interval: int

    active: bool = Field(index=True, default=True)
    order: int = Field(default=0)

    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )
