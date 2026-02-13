from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field


class Meta(BaseModel):
    """Untyped by default. Override to add structured metadata with defaults.

    Example:
        class Meta(BaseModel):
            model_config = ConfigDict(extra="allow")
            confidence: float = 0.0
            strategy: str = "default"
    """

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

    subject: str = "BTC"
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


def default_resolve_ground_truth(feed_records: list[Any]) -> dict[str, Any] | None:
    """Default resolver: compare first and last record's close/price in the window.

    Override for custom ground truth (VWAP, cross-venue, labels, etc.).
    Receives FeedRecord objects with .values dict and .ts_event.
    """
    if len(feed_records) < 1:
        return None

    def _price(record: Any) -> float | None:
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


FRAC_64_MULTIPLIER = 1_000_000_000  # 100% in on-chain frac64 representation


def pct_to_frac64(pct: float) -> int:
    """Convert percentage (0-100) to frac64 (0 to FRAC_64_MULTIPLIER)."""
    return int(round(pct / 100.0 * FRAC_64_MULTIPLIER))


def default_build_emission(
    ranked_entries: list[dict[str, Any]],
    crunch_pubkey: str,
    compute_provider: str | None = None,
    data_provider: str | None = None,
) -> dict[str, Any]:
    """Build EmissionCheckpoint from ranked entries.

    Default tiers: 1st=35%, 2-5=10%, 6-10=5%. Unclaimed redistributed equally.
    All cruncher reward_pcts sum to exactly FRAC_64_MULTIPLIER.
    """
    tiers = [(1, 1, 35.0), (2, 5, 10.0), (6, 10, 5.0)]

    raw_pcts = []
    for entry in ranked_entries:
        rank = entry.get("rank", 0)
        pct = next((t for s, e, t in tiers if s <= rank <= e), 0.0)
        raw_pcts.append(pct)

    total_raw = sum(raw_pcts)
    if total_raw < 100.0 and ranked_entries:
        remainder_each = (100.0 - total_raw) / len(ranked_entries)
        raw_pcts = [p + remainder_each for p in raw_pcts]

    frac64_values = [pct_to_frac64(p) for p in raw_pcts]
    if frac64_values:
        frac64_values[0] += FRAC_64_MULTIPLIER - sum(frac64_values)

    return {
        "crunch": crunch_pubkey,
        "cruncher_rewards": [
            {"cruncher_index": i, "reward_pct": frac64_values[i]}
            for i in range(len(ranked_entries))
        ],
        "compute_provider_rewards": [
            {"provider": compute_provider, "reward_pct": FRAC_64_MULTIPLIER}
        ] if compute_provider else [],
        "data_provider_rewards": [
            {"provider": data_provider, "reward_pct": FRAC_64_MULTIPLIER}
        ] if data_provider else [],
    }


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

    # On-chain identifiers
    crunch_pubkey: str = Field(default="", description="Crunch account pubkey for emission checkpoints")
    compute_provider: str | None = Field(default=None, description="Compute provider wallet pubkey")
    data_provider: str | None = Field(default=None, description="Data provider wallet pubkey")

    # Callables
    resolve_ground_truth: Callable[[list[Any]], dict[str, Any] | None] = default_resolve_ground_truth
    aggregate_snapshot: Callable[[list[dict[str, Any]]], dict[str, Any]] = default_aggregate_snapshot
    build_emission: Callable[..., dict[str, Any]] = default_build_emission
