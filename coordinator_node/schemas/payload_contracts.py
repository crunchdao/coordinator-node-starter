from __future__ import annotations

from typing import Any, Literal

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


# ---------------------------------------------------------------------------
# Report schema contracts — must match coordinator-webapp FE types
# ---------------------------------------------------------------------------


class ReportLeaderboardColumn(BaseModel):
    """Matches FE LeaderboardColumn type in @coordinator/leaderboard."""

    id: int
    type: Literal["MODEL", "VALUE", "USERNAME", "CHART"]
    property: str
    format: str | None = None
    displayName: str
    tooltip: str | None = None
    nativeConfiguration: dict[str, Any] | None = None
    order: int = 0

    model_config = ConfigDict(extra="allow")


class ReportMetricWidget(BaseModel):
    """Matches FE Widget type in @coordinator/metrics."""

    id: int
    type: Literal["CHART", "IFRAME"]
    displayName: str
    tooltip: str | None = None
    order: int = 0
    endpointUrl: str
    nativeConfiguration: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


class ReportSchemaEnvelope(BaseModel):
    """Validated report schema returned by REPORT_SCHEMA_PROVIDER callables.

    Ensures every leaderboard column and metric widget has all required
    fields so the coordinator-webapp FE can render without errors.
    """

    schema_version: str = "1"
    leaderboard_columns: list[ReportLeaderboardColumn]
    metrics_widgets: list[ReportMetricWidget]

    model_config = ConfigDict(extra="allow")
