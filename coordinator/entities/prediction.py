from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


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
    status: str = "RECEIVED"  # RECEIVED → RESOLVED
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
    status: str  # PENDING, SCORED, FAILED, ABSENT
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
