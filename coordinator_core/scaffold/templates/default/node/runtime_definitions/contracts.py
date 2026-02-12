from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MarketInput(BaseModel):
    """What the feed produces. Shape is determined by feed config."""

    model_config = ConfigDict(extra="allow")

    symbol: str = "BTC"
    asof_ts: int = 0
    candles_1m: list[dict] = Field(default_factory=list)


class InferenceInput(MarketInput):
    """What models receive. Same as MarketInput unless you override.

    To transform market data before it reaches models, define a different
    shape here and provide a transform function:

        class InferenceInput(BaseModel):
            symbol: str
            momentum: float

        def transform(market: MarketInput) -> InferenceInput:
            candles = market.candles_1m
            momentum = candles[-1]["close"] - candles[0]["close"] if candles else 0.0
            return InferenceInput(symbol=market.symbol, momentum=momentum)
    """

    pass


class InferenceOutput(BaseModel):
    """What models must return. Customize fields to match your prediction format."""

    value: float = Field(default=0.0)


class ScoreResult(BaseModel):
    """What scoring produces. Customize metrics fields for your challenge."""

    value: float = 0.0
    success: bool = True
    failed_reason: str | None = None


class PredictionScope(BaseModel):
    """What defines a single prediction context — passed to model.predict()."""

    model_config = ConfigDict(extra="allow")

    asset: str = "BTC"
    horizon_seconds: int = Field(default=60, ge=1)
    step_seconds: int = Field(default=15, ge=1)


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

    market_input_type: type[BaseModel] = MarketInput
    input_type: type[BaseModel] = InferenceInput
    output_type: type[BaseModel] = InferenceOutput
    score_type: type[BaseModel] = ScoreResult
    scope: PredictionScope = Field(default_factory=PredictionScope)
    aggregation: Aggregation = Field(default_factory=Aggregation)
