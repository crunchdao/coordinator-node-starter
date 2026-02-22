"""Competition-specific CrunchConfig override.

Imports all base types and defaults from the coordinator-node library.
Only defines what's different for this competition.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from coordinator_node.crunch_config import (
    CrunchConfig as BaseCrunchConfig,
    Meta,
    GroundTruth,
    InferenceOutput,
    ScoreResult,
    PredictionScope,
    Aggregation,
)


class RawInput(BaseModel):
    """What the feed produces. Multi-timeframe OHLCV + microstructure data."""

    model_config = ConfigDict(extra="allow")

    symbol: str = "BTC"
    asof_ts: int = 0

    # Multi-timeframe OHLCV candles (aggregated from 1m)
    candles_1m: list[dict] = Field(default_factory=list)
    candles_5m: list[dict] = Field(default_factory=list)
    candles_15m: list[dict] = Field(default_factory=list)
    candles_1h: list[dict] = Field(default_factory=list)

    # Order book microstructure (latest snapshot, or None if unavailable)
    orderbook: dict | None = Field(default=None)

    # Funding rate / basis (latest, or None if unavailable)
    funding: dict | None = Field(default=None)


class InferenceInput(RawInput):
    """What models receive. Same as RawInput unless you override.

    To transform market data before it reaches models, define a different
    shape here and provide a transform function:

        class InferenceInput(BaseModel):
            symbol: str
            momentum: float

        def transform(market: RawInput) -> InferenceInput:
            candles = market.candles_1m
            momentum = candles[-1]["close"] - candles[0]["close"] if candles else 0.0
            return InferenceInput(symbol=market.symbol, momentum=momentum)
    """

    pass


class CrunchConfig(BaseCrunchConfig):
    """Competition config — overrides all data-shape types.

    All five types are listed explicitly so you see what needs customization:
      - raw_input_type:    What the feed produces (market data shape)
      - ground_truth_type: What the actual outcome looks like
      - input_type:        What models receive (can transform from RawInput)
      - output_type:       What models must return (prediction format)
      - score_type:        What scoring produces (metrics/result fields)

    Customize output_type when your models return something other than
    a single float (e.g. trade orders, multi-field predictions).
    Customize score_type when your scoring produces additional metrics
    beyond the default 'value' field.
    """

    raw_input_type: type[BaseModel] = RawInput
    ground_truth_type: type[BaseModel] = GroundTruth
    input_type: type[BaseModel] = InferenceInput
    output_type: type[BaseModel] = InferenceOutput      # ← customize for your prediction format
    score_type: type[BaseModel] = ScoreResult            # ← customize for your scoring metrics
