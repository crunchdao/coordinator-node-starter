from __future__ import annotations

from typing import Any


def default_build_inference_input(raw_input: dict[str, Any]) -> dict[str, Any]:
    """Default input builder: pass source payload through unchanged."""
    return raw_input


def default_validate_inference_output(inference_output: dict[str, Any]) -> dict[str, Any]:
    """Default inference-output validator: no-op pass-through."""
    return inference_output


def default_score_prediction(prediction: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    """Default scoring callable placeholder for template runtime wiring."""
    return {
        "value": 0.0,
        "success": True,
        "failed_reason": None,
    }


def default_aggregate_model_scores(scored_predictions: list[Any], models: dict[str, Any]) -> list[dict[str, Any]]:
    """Default aggregator: compute per-model average score and expose rankable entries."""
    by_model: dict[str, list[float]] = {}

    for prediction in scored_predictions:
        score = getattr(prediction, "score", None)
        if score is None:
            continue
        if not getattr(score, "success", False):
            continue
        value = getattr(score, "value", None)
        if value is None:
            continue

        by_model.setdefault(str(prediction.model_id), []).append(float(value))

    entries: list[dict[str, Any]] = []
    for model_id, values in by_model.items():
        if not values:
            continue

        average = sum(values) / len(values)
        model = models.get(model_id)

        entries.append(
            {
                "model_id": model_id,
                "score_recent": average,
                "score_steady": average,
                "score_anchor": average,
                "model_name": getattr(model, "name", None),
                "cruncher_name": getattr(model, "player_name", None),
            }
        )

    return entries


def default_rank_leaderboard(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Default ranker: descending by score_anchor and assign ranks."""
    sorted_entries = sorted(entries, key=lambda entry: float(entry.get("score_anchor", float("-inf"))), reverse=True)

    ranked = []
    for idx, entry in enumerate(sorted_entries, start=1):
        ranked.append({**entry, "rank": idx})

    return ranked


def invalid_score_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    """Intentionally invalid signature used by tests for resolver validation."""
    return {"value": 0.0, "success": True, "failed_reason": None}
