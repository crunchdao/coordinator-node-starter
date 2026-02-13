from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Hardcoded realtime defaults — the only pack we ship.
_CHECKPOINT_INTERVAL_SECONDS = 15
_SCORING_CALLABLE = "{package_module}.scoring:score_prediction"
_SCHEDULED_PREDICTION_CONFIGS: list[dict[str, Any]] = [
    {
        "scope_key": "realtime-btc",
        "scope_template": {},
        "schedule": {"every_seconds": 15},
        "active": True,
        "order": 0,
    },
]


@dataclass(frozen=True)
class InitConfig:
    name: str
    package_module: str
    node_name: str
    challenge_name: str
    crunch_id: str
    model_base_classname: str
    checkpoint_interval_seconds: int
    callables: dict[str, str]
    scheduled_prediction_configs: list[dict[str, Any]]


def is_valid_slug(name: str) -> bool:
    return bool(_SLUG_PATTERN.fullmatch(name or ""))


def resolve_init_config(name: str) -> InitConfig:
    if not name:
        raise ValueError("Challenge name required.")
    if not is_valid_slug(name):
        raise ValueError(
            "Invalid challenge name. Use lowercase slug format like 'btc-trader' "
            "(letters, numbers, single dashes)."
        )

    package_module = f"crunch_{name.replace('-', '_')}"

    return InitConfig(
        name=name,
        package_module=package_module,
        node_name=f"crunch-node-{name}",
        challenge_name=f"crunch-{name}",
        crunch_id="starter-challenge",
        model_base_classname="tracker.TrackerBase",
        checkpoint_interval_seconds=_CHECKPOINT_INTERVAL_SECONDS,
        callables={
            "SCORING_FUNCTION": _SCORING_CALLABLE.format(package_module=package_module),
        },
        scheduled_prediction_configs=_SCHEDULED_PREDICTION_CONFIGS,
    )
