from __future__ import annotations

from typing import Any

from node_template.extensions.default_callables import (
    default_aggregate_model_scores,
    default_build_inference_input,
    default_build_predict_call,
    default_build_prediction_scope,
    default_provide_raw_input,
    default_rank_leaderboard,
    default_report_schema,
    default_resolve_ground_truth,
    default_score_prediction,
    default_validate_inference_output,
)


def build_input(raw_input: dict[str, Any]) -> dict[str, Any]:
    return default_build_inference_input(raw_input)


def validate_output(inference_output: dict[str, Any]) -> dict[str, Any]:
    return default_validate_inference_output(inference_output)


def score_prediction(prediction: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    return default_score_prediction(prediction, ground_truth)


def aggregate_model_scores(scored_predictions: list[Any], models: dict[str, Any]) -> list[dict[str, Any]]:
    return default_aggregate_model_scores(scored_predictions, models)


def report_schema() -> dict[str, Any]:
    return default_report_schema()


def rank_leaderboard(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return default_rank_leaderboard(entries)


def provide_raw_input(now):
    return default_provide_raw_input(now)


def resolve_ground_truth(prediction: Any) -> dict[str, Any]:
    return default_resolve_ground_truth(prediction)


def build_prediction_scope(config: dict[str, Any], inference_input: dict[str, Any]) -> dict[str, Any]:
    return default_build_prediction_scope(config, inference_input)


def build_predict_call(config: dict[str, Any], inference_input: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
    return default_build_predict_call(config, inference_input, scope)
