from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def default_build_inference_input(raw_input: dict[str, Any]) -> dict[str, Any]:
    """Default input builder: pass source payload through unchanged."""
    return raw_input


def default_validate_inference_output(inference_output: dict[str, Any]) -> dict[str, Any]:
    """Default inference-output validator: no-op pass-through."""
    return inference_output


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


def default_build_prediction_scope(config: dict[str, Any], inference_input: dict[str, Any]) -> dict[str, Any]:
    """Build generic prediction scope from config template."""
    scope = dict(config.get("scope_template") or {})
    return {
        "scope_key": str(config.get("scope_key") or "default-scope"),
        "scope": scope,
    }


def default_build_predict_call(config: dict[str, Any], inference_input: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    """Build model predict invocation args from generic scope.

    Default keeps backward compatibility with starter tracker signatures: predict(asset, horizon, step).
    """
    scope_payload = scope.get("scope") if isinstance(scope, dict) else {}
    if not isinstance(scope_payload, dict):
        scope_payload = {}

    asset = scope_payload.get("asset", "BTC")
    horizon = int(scope_payload.get("horizon", scope_payload.get("horizon_seconds", 60)))
    step = int(scope_payload.get("step", scope_payload.get("step_seconds", horizon)))

    return {
        "args": [asset, horizon, step],
        "kwargs": {},
    }


def default_resolve_resolvable_at(config: dict[str, Any], now: datetime, scope: dict[str, Any]) -> datetime:
    schedule = config.get("schedule") if isinstance(config, dict) else None
    schedule = schedule if isinstance(schedule, dict) else {}

    resolve_after_seconds = schedule.get("resolve_after_seconds")
    if resolve_after_seconds is None:
        scope_payload = scope.get("scope") if isinstance(scope, dict) else {}
        if isinstance(scope_payload, dict):
            resolve_after_seconds = scope_payload.get("horizon", scope_payload.get("horizon_seconds", 0))

    try:
        seconds = int(resolve_after_seconds or 0)
    except Exception:
        seconds = 0

    return now + timedelta(seconds=max(0, seconds))


def default_aggregate_model_scores(scored_predictions: list[Any], models: dict[str, Any]) -> list[dict[str, Any]]:
    """Default aggregator: compute per-model average score and expose generic score envelopes."""
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
                "score": {
                    "metrics": {
                        "average": average,
                    },
                    "ranking": {
                        "key": "average",
                        "value": average,
                        "direction": "desc",
                    },
                    "payload": {},
                },
                "model_name": getattr(model, "name", None),
                "cruncher_name": getattr(model, "player_name", None),
            }
        )

    return entries


def default_rank_leaderboard(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Default ranker honoring score.ranking.direction and score.ranking key/value."""

    def _rank_value(entry: dict[str, Any]) -> float:
        score = entry.get("score")
        if not isinstance(score, dict):
            return float("-inf")

        metrics = score.get("metrics") if isinstance(score.get("metrics"), dict) else {}
        ranking = score.get("ranking") if isinstance(score.get("ranking"), dict) else {}
        direction = str(ranking.get("direction", "desc")).lower()

        value = ranking.get("value")
        if value is None:
            ranking_key = ranking.get("key")
            if isinstance(ranking_key, str):
                value = metrics.get(ranking_key)

        try:
            numeric = float(value)
        except Exception:
            return float("-inf")

        return -numeric if direction == "asc" else numeric

    sorted_entries = sorted(entries, key=_rank_value, reverse=True)

    ranked = []
    for idx, entry in enumerate(sorted_entries, start=1):
        ranked.append({**entry, "rank": idx})

    return ranked


def invalid_score_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    """Intentionally invalid signature used by tests for resolver validation."""
    return {"value": 0.0, "success": True, "failed_reason": None}
