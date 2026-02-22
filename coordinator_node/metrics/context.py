"""Metrics evaluation context — shared state for cross-model metrics."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class MetricsContext:
    """Context passed to each metric function during evaluation.

    Built once per score cycle and shared across all model evaluations,
    so cross-model metrics (correlation, contribution) don't re-fetch data.
    """

    model_id: str
    window_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    window_end: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # All models' predictions in this window: model_id → list of prediction dicts
    all_model_predictions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    # Ensemble predictions (if ensembling enabled): ensemble_name → list of prediction dicts
    ensemble_predictions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
