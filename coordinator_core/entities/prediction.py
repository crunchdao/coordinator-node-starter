from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class PredictionScore:
    value: float | None
    success: bool
    failed_reason: str | None
    scored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PredictionRecord:
    id: str
    model_id: str
    prediction_config_id: str | None
    scope_key: str
    scope: dict[str, Any]
    status: str  # PENDING, RESOLVED, SCORED, FAILED, ABSENT
    exec_time_ms: float
    inference_input: dict[str, Any] = field(default_factory=dict)
    inference_output: dict[str, Any] = field(default_factory=dict)
    actuals: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    performed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolvable_at: datetime | None = None
    score: PredictionScore | None = None
