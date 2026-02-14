from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, TypedDict


class InputStatus(StrEnum):
    RECEIVED = "RECEIVED"
    RESOLVED = "RESOLVED"


class PredictionStatus(StrEnum):
    PENDING = "PENDING"
    SCORED = "SCORED"
    FAILED = "FAILED"
    ABSENT = "ABSENT"


class CheckpointStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    CLAIMABLE = "CLAIMABLE"
    PAID = "PAID"


@dataclass
class InputRecord:
    """A data point received from the feed. Actuals filled in after horizon passes.

    TODO: Consider adding feed_record_id FK for 1:1 lineage (FeedRecord → InputRecord).
    Most realtime setups have one feed event per input. Currently raw_data holds a copy
    which also supports assembled/windowed inputs, but the common case is passthrough.
    """
    id: str
    raw_data: dict[str, Any] = field(default_factory=dict)       # contract.raw_input_type
    actuals: dict[str, Any] | None = None                        # contract.ground_truth_type
    status: InputStatus = InputStatus.RECEIVED
    scope: dict[str, Any] = field(default_factory=dict)          # contract.scope_type (PredictionScope)
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolvable_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)           # contract.meta_type (Meta)


@dataclass
class PredictionRecord:
    """What a model predicted. Links to the input it was based on."""
    id: str
    input_id: str
    model_id: str
    prediction_config_id: str | None
    scope_key: str
    scope: dict[str, Any]                                        # contract.scope_type (PredictionScope)
    status: PredictionStatus
    exec_time_ms: float
    inference_output: dict[str, Any] = field(default_factory=dict)  # contract.output_type (InferenceOutput)
    meta: dict[str, Any] = field(default_factory=dict)           # contract.meta_type (Meta)
    performed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolvable_at: datetime | None = None


@dataclass
class ScoreRecord:
    """Scoring result for a prediction."""
    id: str
    prediction_id: str
    result: dict[str, Any] = field(default_factory=dict)         # contract.score_type (ScoreResult)
    success: bool = True
    failed_reason: str | None = None
    scored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def value(self) -> float | None:
        """Shortcut to result['value'] (the primary score metric)."""
        v = self.result.get("value")
        return float(v) if v is not None else None


@dataclass
class ScoredPrediction:
    """Prediction with its score attached (used by report endpoints)."""
    id: str
    input_id: str
    model_id: str
    prediction_config_id: str | None
    scope_key: str
    scope: dict[str, Any]
    status: PredictionStatus
    exec_time_ms: float
    inference_output: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    performed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolvable_at: datetime | None = None
    score: ScoreRecord | None = None


@dataclass
class SnapshotRecord:
    """Per-model period summary. Written after each score cycle."""
    id: str
    model_id: str
    period_start: datetime
    period_end: datetime
    prediction_count: int = 0
    result_summary: dict[str, Any] = field(default_factory=dict) # contract.aggregate_snapshot output
    meta: dict[str, Any] = field(default_factory=dict)           # contract.meta_type (Meta)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CruncherReward(TypedDict):
    """On-chain cruncher reward. reward_pct is frac64 (1_000_000_000 = 100%)."""
    cruncher_index: int
    reward_pct: int  # frac64: sum of all cruncher rewards must equal FRAC_64_MULTIPLIER


class ProviderReward(TypedDict):
    """On-chain provider reward. reward_pct is frac64 (1_000_000_000 = 100%)."""
    provider: str   # wallet pubkey
    reward_pct: int  # frac64


class EmissionCheckpoint(TypedDict):
    """Protocol-format emission checkpoint for on-chain submission."""
    crunch: str  # crunch pubkey
    cruncher_rewards: list[CruncherReward]
    compute_provider_rewards: list[ProviderReward]
    data_provider_rewards: list[ProviderReward]


@dataclass
class CheckpointRecord:
    """Weekly aggregation of snapshots → on-chain payout."""
    id: str
    period_start: datetime
    period_end: datetime
    status: CheckpointStatus = CheckpointStatus.PENDING
    entries: list[EmissionCheckpoint] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tx_hash: str | None = None
    submitted_at: datetime | None = None
