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

    overall_score_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )
    scores_by_scope_jsonb: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    created_at: datetime = Field(default_factory=utc_now, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)


class InputRow(SQLModel, table=True):
    __tablename__ = "inputs"

    id: str = Field(primary_key=True)
    status: str = Field(default="RECEIVED", index=True)

    raw_data_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )
    actuals_jsonb: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    scope_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    received_at: datetime = Field(default_factory=utc_now, index=True)
    resolvable_at: Optional[datetime] = Field(default=None, index=True)


class PredictionRow(SQLModel, table=True):
    __tablename__ = "predictions"

    id: str = Field(primary_key=True)
    input_id: str = Field(index=True, foreign_key="inputs.id")
    model_id: str = Field(index=True, foreign_key="models.id")
    prediction_config_id: Optional[str] = Field(default=None, foreign_key="scheduled_prediction_configs.id", index=True)

    scope_key: str = Field(index=True)
    scope_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    status: str = Field(index=True)
    exec_time_ms: float

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

    __table_args__ = (
        Index("idx_predictions_lookup", "model_id", "scope_key"),
    )


class ScoreRow(SQLModel, table=True):
    __tablename__ = "scores"

    id: str = Field(primary_key=True)
    prediction_id: str = Field(index=True, foreign_key="predictions.id")

    value: Optional[float] = None
    success: Optional[bool] = None
    failed_reason: Optional[str] = None
    scored_at: datetime = Field(default_factory=utc_now, index=True)


class ModelScoreRow(SQLModel, table=True):
    __tablename__ = "model_scores"

    id: str = Field(primary_key=True)
    model_id: str = Field(index=True, foreign_key="models.id")

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
    __tablename__ = "scheduled_prediction_configs"

    id: str = Field(primary_key=True)

    scope_key: str = Field(index=True)
    scope_template_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )
    schedule_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    active: bool = Field(index=True, default=True)
    order: int = Field(default=0)

    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )


class MarketRecordRow(SQLModel, table=True):
    __tablename__ = "market_records"

    id: str = Field(primary_key=True)

    provider: str = Field(index=True)
    asset: str = Field(index=True)
    kind: str = Field(index=True)
    granularity: str = Field(index=True)

    ts_event: datetime = Field(index=True)
    ts_ingested: datetime = Field(default_factory=utc_now, index=True)

    values_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    __table_args__ = (
        Index(
            "uq_market_records_event",
            "provider",
            "asset",
            "kind",
            "granularity",
            "ts_event",
            unique=True,
        ),
    )


class MarketIngestionStateRow(SQLModel, table=True):
    __tablename__ = "market_ingestion_state"

    id: str = Field(primary_key=True)

    provider: str = Field(index=True)
    asset: str = Field(index=True)
    kind: str = Field(index=True)
    granularity: str = Field(index=True)

    last_event_ts: Optional[datetime] = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=utc_now, index=True)

    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
    )

    __table_args__ = (
        Index(
            "uq_market_ingestion_scope",
            "provider",
            "asset",
            "kind",
            "granularity",
            unique=True,
        ),
    )
