from __future__ import annotations

from datetime import datetime
from typing import Any


def default_provide_raw_input(now: datetime) -> dict[str, Any]:
    """Default raw-input provider: no-op empty payload."""
    return {}


def default_resolve_ground_truth(prediction: Any) -> dict[str, Any]:
    """Default ground-truth resolver: no-op empty payload."""
    return {}


def default_score_prediction(prediction: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    """Default scoring callable placeholder for template runtime wiring."""
    return {
        "value": 0.0,
        "success": True,
        "failed_reason": None,
    }


def invalid_score_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    """Intentionally invalid signature used by tests for resolver validation."""
    return {"value": 0.0, "success": True, "failed_reason": None}
