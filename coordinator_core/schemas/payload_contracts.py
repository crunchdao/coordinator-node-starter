from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScheduleEnvelope(BaseModel):
    """Canonical scheduling envelope stored in `scheduled_prediction_configs.schedule_jsonb`."""

    prediction_interval_seconds: int = Field(default=60, ge=1)
    resolve_after_seconds: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="allow")


class ScheduledPredictionConfigEnvelope(BaseModel):
    """Canonical envelope for active scheduled prediction configs."""

    id: str | None = None
    scope_key: str = Field(min_length=1)
    scope_template: dict[str, Any] = Field(default_factory=dict)
    schedule: ScheduleEnvelope = Field(default_factory=ScheduleEnvelope)
    active: bool = True
    order: int = 0
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class PredictionScopeEnvelope(BaseModel):
    """Canonical scope envelope written to prediction rows."""

    scope_key: str = Field(min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ScoreEnvelope(BaseModel):
    """Canonical score envelope used in model/leaderboard JSONB payloads."""

    windows: dict[str, float | None] = Field(default_factory=dict)
    rank_key: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class LeaderboardEntryEnvelope(BaseModel):
    """Canonical leaderboard entry envelope persisted in `leaderboards.entries_jsonb`."""

    model_id: str
    score: ScoreEnvelope = Field(default_factory=ScoreEnvelope)
    rank: int | None = None
    model_name: str | None = None
    cruncher_name: str | None = None

    model_config = ConfigDict(extra="allow")
