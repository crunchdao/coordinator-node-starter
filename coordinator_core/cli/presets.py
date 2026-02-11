from __future__ import annotations

from copy import deepcopy
from typing import Any

_DEFAULT_PRESET_CALLABLES = {
    "INFERENCE_INPUT_BUILDER": "{package_module}.inference:build_input",
    "INFERENCE_OUTPUT_VALIDATOR": "{package_module}.validation:validate_output",
    "SCORING_FUNCTION": "{package_module}.scoring:score_prediction",
    "MODEL_SCORE_AGGREGATOR": "coordinator_runtime.defaults:aggregate_model_scores",
    "REPORT_SCHEMA_PROVIDER": "{package_module}.reporting:report_schema",
    "LEADERBOARD_RANKER": "coordinator_runtime.defaults:rank_leaderboard",
    "RAW_INPUT_PROVIDER": "coordinator_runtime.defaults:provide_raw_input",
    "GROUND_TRUTH_RESOLVER": "coordinator_runtime.defaults:resolve_ground_truth",
    "PREDICTION_SCOPE_BUILDER": "coordinator_runtime.defaults:build_prediction_scope",
    "PREDICT_CALL_BUILDER": "coordinator_runtime.defaults:build_predict_call",
}

_PRESETS: dict[str, dict[str, Any]] = {
    "baseline": {
        "description": "Balanced default profile for local development.",
        "checkpoint_interval_seconds": 60,
        "callables": _DEFAULT_PRESET_CALLABLES,
        "scheduled_prediction_configs": [
            {
                "scope_key": "default",
                "scope_template": {
                    "asset": "BTC",
                    "horizon_seconds": 60,
                    "step_seconds": 60,
                },
                "schedule": {"every_seconds": 60},
                "active": True,
                "order": 0,
            }
        ],
    },
    "realtime": {
        "description": "Low-latency tournament profile for short horizon updates.",
        "checkpoint_interval_seconds": 15,
        "callables": _DEFAULT_PRESET_CALLABLES,
        "scheduled_prediction_configs": [
            {
                "scope_key": "realtime-btc",
                "scope_template": {
                    "asset": "BTC",
                    "horizon_seconds": 60,
                    "step_seconds": 15,
                    "tournament_mode": "realtime",
                },
                "schedule": {"every_seconds": 15},
                "active": True,
                "order": 0,
            }
        ],
    },
    "in-sample": {
        "description": "In-sample tournament profile for calibration and quick iteration.",
        "checkpoint_interval_seconds": 60,
        "callables": _DEFAULT_PRESET_CALLABLES,
        "scheduled_prediction_configs": [
            {
                "scope_key": "in-sample-btc",
                "scope_template": {
                    "asset": "BTC",
                    "horizon_seconds": 300,
                    "step_seconds": 60,
                    "tournament_mode": "in-sample",
                },
                "schedule": {"every_seconds": 300},
                "active": True,
                "order": 0,
            }
        ],
    },
    "out-of-sample": {
        "description": "Out-of-sample tournament profile for holdout evaluation.",
        "checkpoint_interval_seconds": 300,
        "callables": _DEFAULT_PRESET_CALLABLES,
        "scheduled_prediction_configs": [
            {
                "scope_key": "out-of-sample-btc",
                "scope_template": {
                    "asset": "BTC",
                    "horizon_seconds": 900,
                    "step_seconds": 300,
                    "tournament_mode": "out-of-sample",
                },
                "schedule": {"every_seconds": 900},
                "active": True,
                "order": 0,
            }
        ],
    },
}


def list_preset_names() -> list[str]:
    return sorted(_PRESETS.keys())


def list_preset_summaries() -> list[tuple[str, str]]:
    return [(name, str(_PRESETS[name].get("description", ""))) for name in list_preset_names()]


def get_preset(name: str) -> dict[str, Any]:
    preset_name = str(name or "").strip()
    if not preset_name:
        raise ValueError("Preset name cannot be empty")

    preset = _PRESETS.get(preset_name)
    if preset is None:
        allowed = ", ".join(list_preset_names())
        raise ValueError(f"Unknown preset '{preset_name}'. Allowed presets: {allowed}")

    result = deepcopy(preset)
    result["name"] = preset_name
    return result
