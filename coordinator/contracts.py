from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from coordinator.entities.feed_record import FeedRecord


class Meta(BaseModel):
    """Untyped by default. Override to add structured metadata with defaults."""

    model_config = ConfigDict(extra="allow")


class RawInput(BaseModel):
    """What the feed produces. Shape is determined by feed config."""

    model_config = ConfigDict(extra="allow")

    symbol: str = "BTC"
    asof_ts: int = 0
    candles_1m: list[dict] = Field(default_factory=list)


class GroundTruth(RawInput):
    """What the actual outcome looks like. Same shape as RawInput unless you override."""

    pass


class InferenceInput(RawInput):
    """What models receive. Same as RawInput unless you override."""

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


def default_resolve_ground_truth(feed_records: list[FeedRecord]) -> dict[str, Any] | None:
    """Default resolver: compare first and last record's close/price in the window.

    Override for custom ground truth (VWAP, cross-venue, labels, etc.).
    """
    if len(feed_records) < 1:
        return None

    def _price(record: FeedRecord) -> float | None:
        values = record.values or {}
        for key in ("close", "price"):
            if key in values:
                try:
                    return float(values[key])
                except Exception:
                    pass
        return None

    entry = feed_records[0]
    resolved = feed_records[-1]
    entry_price = _price(entry)
    resolved_price = _price(resolved)

    if entry_price is None or resolved_price is None:
        return None

    return {
        "entry_price": entry_price,
        "resolved_price": resolved_price,
        "return": (resolved_price - entry_price) / max(abs(entry_price), 1e-9),
        "direction_up": resolved_price > entry_price,
    }


def default_aggregate_snapshot(score_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Default aggregator: average all numeric values across score results in the period."""
    if not score_results:
        return {}

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for result in score_results:
        for key, value in result.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0.0) + float(value)
                counts[key] = counts.get(key, 0) + 1

    return {key: totals[key] / counts[key] for key in totals}


class CrunchContract(BaseModel):
    """Single source of truth for challenge data shapes and aggregation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    meta_type: type[BaseModel] = Meta
    raw_input_type: type[BaseModel] = RawInput
    ground_truth_type: type[BaseModel] = GroundTruth
    input_type: type[BaseModel] = InferenceInput
    output_type: type[BaseModel] = InferenceOutput
    score_type: type[BaseModel] = ScoreResult
    scope: PredictionScope = Field(default_factory=PredictionScope)
    aggregation: Aggregation = Field(default_factory=Aggregation)

    # Callables
    resolve_ground_truth: Callable[[list[FeedRecord]], dict[str, Any] | None] = default_resolve_ground_truth
    aggregate_snapshot: Callable[[list[dict[str, Any]]], dict[str, Any]] = default_aggregate_snapshot
