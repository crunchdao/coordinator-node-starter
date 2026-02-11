from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BtcScopeSchema(BaseModel):
    asset: Literal["BTC"]
    horizon: int = Field(ge=1)
    step: int = Field(ge=1)

    model_config = ConfigDict(extra="allow")


class ProbabilityUpOutputSchema(BaseModel):
    p_up: float = Field(ge=0.0, le=1.0)


class BtcGroundTruthSchema(BaseModel):
    asset: Literal["BTC"] | None = None
    entry_price: float | None = None
    resolved_price: float | None = None
    resolved_publish_time: int | None = None
    y_up: bool
    source: str | None = None

    model_config = ConfigDict(extra="allow")


class BtcRawInputSchema(BaseModel):
    BTC: list[tuple[int, float]]


class BtcPredictionScopeEnvelope(BaseModel):
    scope_key: str
    scope: BtcScopeSchema
    model_config = ConfigDict(extra="allow")


class FlexiblePredictionScopeSchema(BaseModel):
    """Helper for reading generic prediction scope dictionaries."""

    scope: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow")
