"""Core pipeline tables: inputs → predictions → scores, plus prediction configs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InputRow(SQLModel, table=True):
    __tablename__ = "inputs"

    id: str = Field(primary_key=True)
    status: str = Field(default="RECEIVED", index=True)

    raw_data_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )
    actuals_jsonb: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSONB, nullable=True),
    )
    scope_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )

    received_at: datetime = Field(default_factory=utc_now, index=True)
    resolvable_at: Optional[datetime] = Field(default=None, index=True)


class PredictionRow(SQLModel, table=True):
    __tablename__ = "predictions"

    id: str = Field(primary_key=True)
    input_id: str = Field(index=True, foreign_key="inputs.id")
    model_id: str = Field(index=True, foreign_key="models.id")
    prediction_config_id: Optional[str] = Field(
        default=None, foreign_key="scheduled_prediction_configs.id", index=True,
    )

    scope_key: str = Field(index=True)
    scope_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )

    status: str = Field(index=True)
    exec_time_ms: float

    inference_output_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
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

    result_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )
    success: Optional[bool] = None
    failed_reason: Optional[str] = None
    scored_at: datetime = Field(default_factory=utc_now, index=True)


class SnapshotRow(SQLModel, table=True):
    __tablename__ = "snapshots"

    id: str = Field(primary_key=True)
    model_id: str = Field(index=True, foreign_key="models.id")

    period_start: datetime = Field(index=True)
    period_end: datetime = Field(index=True)
    prediction_count: int = Field(default=0)

    result_summary_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )

    created_at: datetime = Field(default_factory=utc_now, index=True)


class CheckpointRow(SQLModel, table=True):
    __tablename__ = "checkpoints"

    id: str = Field(primary_key=True)

    period_start: datetime = Field(index=True)
    period_end: datetime = Field(index=True)
    status: str = Field(default="PENDING", index=True)

    entries_jsonb: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSONB),
    )
    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )

    created_at: datetime = Field(default_factory=utc_now, index=True)
    tx_hash: Optional[str] = Field(default=None)
    submitted_at: Optional[datetime] = Field(default=None)


class PredictionConfigRow(SQLModel, table=True):
    __tablename__ = "scheduled_prediction_configs"

    id: str = Field(primary_key=True)

    scope_key: str = Field(index=True)
    scope_template_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )
    schedule_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )

    active: bool = Field(index=True, default=True)
    order: int = Field(default=0)

    meta_jsonb: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB),
    )
