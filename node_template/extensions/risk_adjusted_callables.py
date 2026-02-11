from __future__ import annotations

from statistics import fmean, pstdev
from typing import Any

RISK_SCORE_SERIES: list[dict[str, str]] = [
    {"name": "score_sharpe_like", "label": "Sharpe-like"},
    {"name": "score_wealth", "label": "Wealth"},
    {"name": "score_mean_return", "label": "Mean Return"},
    {"name": "score_volatility", "label": "Volatility"},
]


def flatten_risk_metrics(metrics: dict[str, Any]) -> dict[str, float | None]:
    return {
        "score_sharpe_like": _to_float(metrics.get("sharpe_like")),
        "score_wealth": _to_float(metrics.get("wealth")),
        "score_mean_return": _to_float(metrics.get("mean_return")),
        "score_volatility": _to_float(metrics.get("volatility")),
        "score_hit_rate": _to_float(metrics.get("hit_rate")),
    }


def risk_adjusted_report_schema() -> dict[str, Any]:
    """Canonical report schema for risk-adjusted profile (Sharpe-like ranking)."""
    return {
        "schema_version": "1",
        "leaderboard_columns": [
            {
                "id": 1,
                "type": "MODEL",
                "property": "model_id",
                "format": None,
                "displayName": "Model",
                "tooltip": None,
                "nativeConfiguration": {"type": "model", "statusProperty": "status"},
                "order": 0,
            },
            {
                "id": 2,
                "type": "VALUE",
                "property": "score_sharpe_like",
                "format": "decimal-3",
                "displayName": "Sharpe-like",
                "tooltip": "Risk-adjusted score: mean return divided by return volatility.",
                "nativeConfiguration": None,
                "order": 20,
            },
            {
                "id": 3,
                "type": "VALUE",
                "property": "score_wealth",
                "format": "decimal-3",
                "displayName": "Wealth",
                "tooltip": "Compounded wealth from realized per-prediction returns.",
                "nativeConfiguration": None,
                "order": 30,
            },
            {
                "id": 4,
                "type": "VALUE",
                "property": "score_mean_return",
                "format": "decimal-4",
                "displayName": "Mean Return",
                "tooltip": "Average realized strategy return per prediction.",
                "nativeConfiguration": None,
                "order": 40,
            },
            {
                "id": 5,
                "type": "VALUE",
                "property": "score_volatility",
                "format": "decimal-4",
                "displayName": "Volatility",
                "tooltip": "Volatility of realized strategy returns.",
                "nativeConfiguration": None,
                "order": 50,
            },
        ],
        "metrics_widgets": [
            {
                "id": 1,
                "type": "CHART",
                "displayName": "Risk-adjusted score metrics",
                "tooltip": None,
                "order": 10,
                "endpointUrl": "/reports/models/global",
                "nativeConfiguration": {
                    "type": "line",
                    "xAxis": {"name": "performed_at"},
                    "yAxis": {"series": RISK_SCORE_SERIES, "format": "decimal-4"},
                    "displayEvolution": False,
                },
            },
            {
                "id": 2,
                "type": "CHART",
                "displayName": "Predictions",
                "tooltip": None,
                "order": 30,
                "endpointUrl": "/reports/predictions",
                "nativeConfiguration": {
                    "type": "line",
                    "xAxis": {"name": "performed_at"},
                    "yAxis": {"series": [{"name": "score_value"}], "format": "decimal-4"},
                    "alertConfig": {"reasonField": "score_failed_reason", "field": "score_success"},
                    "filterConfig": [{"type": "select", "label": "Scope", "property": "scope_key", "autoSelectFirst": True}],
                    "groupByProperty": "scope_key",
                    "displayEvolution": False,
                },
            },
            {
                "id": 3,
                "type": "CHART",
                "displayName": "Rolling risk metrics by scope",
                "tooltip": None,
                "order": 20,
                "endpointUrl": "/reports/models/params",
                "nativeConfiguration": {
                    "type": "line",
                    "xAxis": {"name": "performed_at"},
                    "yAxis": {"series": RISK_SCORE_SERIES, "format": "decimal-4"},
                    "filterConfig": [{"type": "select", "label": "Scope", "property": "scope_key", "autoSelectFirst": True}],
                    "groupByProperty": "scope_key",
                    "displayEvolution": False,
                },
            },
        ],
    }


def aggregate_model_scores_sharpe_like(scored_predictions: list[Any], models: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate per-prediction returns into risk-adjusted leaderboard entries.

    Assumes each `prediction.score.value` is a realized strategy return for one prediction.
    """
    returns_by_model: dict[str, list[float]] = {}

    for prediction in scored_predictions:
        score = getattr(prediction, "score", None)
        if score is None or not getattr(score, "success", False):
            continue

        value = getattr(score, "value", None)
        if value is None:
            continue

        returns_by_model.setdefault(str(prediction.model_id), []).append(float(value))

    entries: list[dict[str, Any]] = []
    for model_id, returns in returns_by_model.items():
        if not returns:
            continue

        metrics = compute_return_metrics(returns)
        model = models.get(model_id)

        entries.append(
            {
                "model_id": model_id,
                "score": {
                    "metrics": metrics,
                    "ranking": {
                        "key": "sharpe_like",
                        "value": metrics.get("sharpe_like"),
                        "direction": "desc",
                        "tie_breakers": ["wealth", "mean_return"],
                    },
                    "payload": {
                        "num_predictions": len(returns),
                    },
                },
                "model_name": getattr(model, "name", None),
                "cruncher_name": getattr(model, "player_name", None),
            }
        )

    return entries


def rank_leaderboard_risk_adjusted(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank by score.ranking and optional tie-breaker metrics."""

    def _rank_value(entry: dict[str, Any]) -> tuple:
        score = entry.get("score") if isinstance(entry.get("score"), dict) else {}
        metrics = score.get("metrics") if isinstance(score.get("metrics"), dict) else {}
        ranking = score.get("ranking") if isinstance(score.get("ranking"), dict) else {}

        direction = str(ranking.get("direction", "desc")).lower()
        key = ranking.get("key")

        primary = ranking.get("value")
        if primary is None and isinstance(key, str):
            primary = metrics.get(key)

        primary_float = _to_float(primary)
        if primary_float is None:
            primary_rank = float("-inf")
        else:
            primary_rank = -primary_float if direction == "asc" else primary_float

        tie_breakers = ranking.get("tie_breakers") if isinstance(ranking.get("tie_breakers"), list) else []
        tie_values = []
        for metric_key in tie_breakers:
            if not isinstance(metric_key, str):
                continue
            tie_values.append(_to_float(metrics.get(metric_key)) or float("-inf"))

        return (primary_rank, *tie_values)

    ranked_entries = sorted(entries, key=_rank_value, reverse=True)
    return [{**entry, "rank": idx} for idx, entry in enumerate(ranked_entries, start=1)]


def compute_return_metrics(returns: list[float]) -> dict[str, float]:
    mean_return = float(fmean(returns))
    volatility = float(pstdev(returns)) if len(returns) > 1 else 0.0

    volatility_floor = 1e-6
    sharpe_like = mean_return / max(volatility, volatility_floor)

    wealth = 1.0
    for r in returns:
        bounded_r = max(-1.0, float(r))
        wealth *= 1.0 + bounded_r

    hit_rate = float(sum(1 for r in returns if r > 0.0) / len(returns))

    return {
        "mean_return": mean_return,
        "volatility": volatility,
        "sharpe_like": float(sharpe_like),
        "wealth": float(wealth),
        "hit_rate": hit_rate,
    }


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
