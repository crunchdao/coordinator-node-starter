from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from coordinator.entities.feed_record import FeedRecord
from coordinator.entities.prediction import CruncherReward, EmissionCheckpoint, ProviderReward


class Meta(BaseModel):
    """Untyped by default. Override to add structured metadata with defaults."""

    model_config = ConfigDict(extra="allow")


class RawInput(BaseModel):
    """What the feed produces. Override to define your feed's data shape."""

    model_config = ConfigDict(extra="allow")


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


FRAC_64_MULTIPLIER = 1_000_000_000  # 100% in on-chain frac64 representation


def pct_to_frac64(pct: float) -> int:
    """Convert percentage (0-100) to frac64 (0 to FRAC_64_MULTIPLIER)."""
    return int(round(pct / 100.0 * FRAC_64_MULTIPLIER))


def default_build_emission(
    ranked_entries: list[dict[str, Any]],
    crunch_pubkey: str,
    compute_provider: str | None = None,
    data_provider: str | None = None,
) -> EmissionCheckpoint:
    """Build an EmissionCheckpoint from ranked entries.

    Default tier distribution (must sum to 100%):
      1st = 35%, 2nd-5th = 10% each, 6th-10th = 5% each, rest split equally.

    All cruncher reward_pcts must sum to exactly FRAC_64_MULTIPLIER.
    Compute/data provider rewards default to 100% for a single provider.
    """
    # Tier definition: (rank_start, rank_end_inclusive, pct_of_100)
    tiers: list[tuple[int, int, float]] = [
        (1, 1, 35.0),
        (2, 5, 10.0),
        (6, 10, 5.0),
    ]

    # Assign raw percentages by tier
    raw_pcts: list[float] = []
    for entry in ranked_entries:
        rank = entry.get("rank", 0)
        pct = 0.0
        for start, end, tier_pct in tiers:
            if start <= rank <= end:
                pct = tier_pct
                break
        raw_pcts.append(pct)

    # Redistribute unclaimed to ensure sum = 100%
    total_raw = sum(raw_pcts)
    if total_raw < 100.0 and len(ranked_entries) > 0:
        # Split remainder equally among all participants
        remainder_each = (100.0 - total_raw) / len(ranked_entries)
        raw_pcts = [p + remainder_each for p in raw_pcts]

    # Convert to frac64, ensuring exact sum = FRAC_64_MULTIPLIER
    frac64_values = [pct_to_frac64(p) for p in raw_pcts]
    if frac64_values:
        diff = FRAC_64_MULTIPLIER - sum(frac64_values)
        frac64_values[0] += diff  # adjust first entry for rounding

    cruncher_rewards: list[CruncherReward] = []
    for i, entry in enumerate(ranked_entries):
        cruncher_rewards.append(CruncherReward(
            cruncher_index=i,
            reward_pct=frac64_values[i],
        ))

    # Default: single compute + data provider each get 100%
    compute_rewards: list[ProviderReward] = []
    if compute_provider:
        compute_rewards.append(ProviderReward(
            provider=compute_provider,
            reward_pct=FRAC_64_MULTIPLIER,
        ))

    data_rewards: list[ProviderReward] = []
    if data_provider:
        data_rewards.append(ProviderReward(
            provider=data_provider,
            reward_pct=FRAC_64_MULTIPLIER,
        ))

    return EmissionCheckpoint(
        crunch=crunch_pubkey,
        cruncher_rewards=cruncher_rewards,
        compute_provider_rewards=compute_rewards,
        data_provider_rewards=data_rewards,
    )


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

    # On-chain identifiers
    crunch_pubkey: str = Field(default="", description="Crunch account pubkey for emission checkpoints")
    compute_provider: str | None = Field(default=None, description="Compute provider wallet pubkey")
    data_provider: str | None = Field(default=None, description="Data provider wallet pubkey")

    # Callables
    resolve_ground_truth: Callable[[list[FeedRecord]], dict[str, Any] | None] = default_resolve_ground_truth
    aggregate_snapshot: Callable[[list[dict[str, Any]]], dict[str, Any]] = default_aggregate_snapshot
    build_emission: Callable[..., EmissionCheckpoint] = default_build_emission
