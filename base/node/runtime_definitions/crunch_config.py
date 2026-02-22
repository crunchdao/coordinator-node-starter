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
    """Competition config — only overrides the data shapes."""

    raw_input_type: type[BaseModel] = RawInput
    ground_truth_type: type[BaseModel] = GroundTruth
    input_type: type[BaseModel] = InferenceInput
