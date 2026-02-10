from __future__ import annotations

from typing import Any


def default_build_inference_input(raw_input: dict[str, Any]) -> dict[str, Any]:
    """Default input builder: pass source payload through unchanged."""
    return raw_input


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
