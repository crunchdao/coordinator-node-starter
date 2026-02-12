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


class PredictionScopeEnvelope(BaseModel):
    """Canonical scope envelope written to prediction rows."""

    scope_key: str = Field(min_length=1)
    scope: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ScoreRankingEnvelope(BaseModel):
    """Ranking strategy for a score payload."""

    key: str | None = None
    value: float | None = None
    direction: Literal["asc", "desc"] = "desc"
    tie_breakers: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class ScoreEnvelope(BaseModel):
    """Canonical score envelope used in model/leaderboard JSONB payloads.

    - metrics: named numeric metrics (wealth, hit_rate, loss, ...)
    - ranking: how to rank these metrics
    - payload: challenge-specific structured details
    """

    metrics: dict[str, float | None] = Field(default_factory=dict)
    ranking: ScoreRankingEnvelope = Field(default_factory=ScoreRankingEnvelope)
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")

    @property
    def rank_value(self) -> float | None:
        if self.ranking.value is not None:
            return float(self.ranking.value)

        if self.ranking.key is None:
            return None

        value = self.metrics.get(self.ranking.key)
        if value is None:
            return None
        return float(value)


class LeaderboardEntryEnvelope(BaseModel):
    """Canonical leaderboard entry envelope persisted in `leaderboards.entries_jsonb`."""

    model_id: str
    score: ScoreEnvelope = Field(default_factory=ScoreEnvelope)
    rank: int | None = None
    model_name: str | None = None
    cruncher_name: str | None = None

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Report schema contracts — must match coordinator-webapp FE types
# ---------------------------------------------------------------------------

_LEADERBOARD_COLUMN_TYPES = {"MODEL", "VALUE", "USERNAME", "CHART"}
_METRIC_WIDGET_TYPES = {"CHART", "IFRAME"}


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
