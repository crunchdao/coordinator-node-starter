from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class InputRecord:
    """A data point received from the feed. Always saved regardless of predictions."""
    id: str
    raw_data: dict[str, Any] = field(default_factory=dict)
    scope: dict[str, Any] = field(default_factory=dict)
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictionScore:
    """Denormalized score view — populated from ScoreRecord when querying."""
    value: float | None = None
    success: bool = True
    failed_reason: str | None = None
    scored_at: datetime | None = None


@dataclass
class PredictionRecord:
    """What a model predicted. Links to the input it was based on."""
    id: str
    input_id: str
    model_id: str
    prediction_config_id: str | None
    scope_key: str
    scope: dict[str, Any]
    status: str  # PENDING, RESOLVED, SCORED, FAILED, ABSENT
    exec_time_ms: float
    inference_output: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    performed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolvable_at: datetime | None = None
    score: PredictionScore | None = None  # populated from ScoreRecord on query


@dataclass
class ScoreRecord:
    """Scoring result for a prediction. Links to the prediction it scored."""
    id: str
    prediction_id: str
    actuals: dict[str, Any] = field(default_factory=dict)
    value: float | None = None
    success: bool = True
    failed_reason: str | None = None
    scored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
