from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InferenceInput(BaseModel):
    """What models receive as input. Customize fields to match your data."""

    model_config = ConfigDict(extra="allow")

    symbol: str = "BTC"
    asof_ts: int = 0
    candles_1m: list[dict] = Field(default_factory=list)


class InferenceOutput(BaseModel):
    """What models must return. Customize fields to match your prediction format."""

    value: float = Field(default=0.0)


class ScoreResult(BaseModel):
    """What scoring produces. Customize metrics fields for your challenge."""

    value: float = 0.0
    success: bool = True
    failed_reason: str | None = None


class AggregationWindow(BaseModel):
    """A rolling time window for score aggregation."""

    hours: int = Field(ge=1)


class Aggregation(BaseModel):
    """How scores are rolled up per model and how the leaderboard is ranked."""

    windows: dict[str, AggregationWindow] = Field(default_factory=lambda: {
        "score_recent": AggregationWindow(hours=24),
        "score_steady": AggregationWindow(hours=72),
        "score_anchor": AggregationWindow(hours=168),
    })
    ranking_key: str = "score_recent"
    ranking_direction: str = "desc"


class CrunchContract(BaseModel):
    """Single source of truth for challenge data shapes and aggregation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    input_type: type[BaseModel] = InferenceInput
    output_type: type[BaseModel] = InferenceOutput
    score_type: type[BaseModel] = ScoreResult
    aggregation: Aggregation = Field(default_factory=Aggregation)
