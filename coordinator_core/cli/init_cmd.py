from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def is_valid_slug(name: str) -> bool:
    return bool(_SLUG_PATTERN.fullmatch(name or ""))


def run_init(name: str, project_root: Path, force: bool = False) -> int:
    if not is_valid_slug(name):
        print(
            "Invalid challenge name. Use lowercase slug format like 'btc-trader' "
            "(letters, numbers, single dashes)."
        )
        return 1

    workspace_dir = project_root / "crunch-implementations" / name
    if workspace_dir.exists():
        if not force:
            print(f"Target already exists: {workspace_dir}. Use --force to overwrite.")
            return 1
        shutil.rmtree(workspace_dir)

    package_module = f"crunch_{name.replace('-', '_')}"
    node_name = f"crunch-node-{name}"
    challenge_name = f"crunch-{name}"

    _write_tree(
        workspace_dir,
        {
            "README.md": _workspace_readme(name),
            f"{node_name}/README.md": _node_readme(name),
            f"{node_name}/pyproject.toml": _node_pyproject(node_name, challenge_name),
            f"{node_name}/.local.env.example": _node_local_env(package_module),
            f"{node_name}/config/README.md": _node_config_readme(),
            f"{node_name}/config/callables.env": _node_callables_env(package_module),
            f"{node_name}/config/scheduled_prediction_configs.json": _scheduled_prediction_configs(),
            f"{node_name}/deployment/README.md": _node_deployment_readme(),
            f"{node_name}/plugins/README.md": _plugins_readme("node"),
            f"{node_name}/extensions/README.md": _extensions_readme("node"),
            f"{challenge_name}/README.md": _challenge_readme(name, package_module),
            f"{challenge_name}/pyproject.toml": _challenge_pyproject(challenge_name, package_module),
            f"{challenge_name}/{package_module}/__init__.py": _challenge_init(),
            f"{challenge_name}/{package_module}/tracker.py": _challenge_tracker(),
            f"{challenge_name}/{package_module}/inference.py": _challenge_inference(),
            f"{challenge_name}/{package_module}/validation.py": _challenge_validation(),
            f"{challenge_name}/{package_module}/scoring.py": _challenge_scoring(),
            f"{challenge_name}/{package_module}/reporting.py": _challenge_reporting(),
            f"{challenge_name}/{package_module}/schemas/README.md": _schemas_readme(),
            f"{challenge_name}/{package_module}/plugins/README.md": _plugins_readme("challenge"),
            f"{challenge_name}/{package_module}/extensions/README.md": _extensions_readme("challenge"),
        },
    )

    print(f"Scaffold created: {workspace_dir}")
    print(f"Next: cd {workspace_dir / node_name}")
    return 0


def _write_tree(base_dir: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = base_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")


def _workspace_readme(name: str) -> str:
    return f"""
# {name} implementation workspace

This workspace contains:

- `crunch-node-{name}`: private node runtime config/deployment wiring
- `crunch-{name}`: public challenge package (schemas/callables/tracker)
"""


def _node_readme(name: str) -> str:
    return f"""
# crunch-node-{name}

Thin node project for `{name}`.

## What belongs here

- deployment and env wiring
- callable path configuration
- optional node-side adapters in `plugins/`
- optional node-side hooks in `extensions/`

Core runtime logic should stay in `coordinator_core`.
"""


def _node_pyproject(node_name: str, challenge_name: str) -> str:
    return f"""
[project]
name = "{node_name}"
version = "0.1.0"
description = "Thin node workspace"
requires-python = ">=3.12,<3.13"
dependencies = [
  "coordinator-node-starter",
  "{challenge_name}",
]

[tool.uv.sources]
coordinator-node-starter = {{ path = "../../..", editable = true }}
{challenge_name} = {{ path = "../{challenge_name}", editable = true }}
"""


def _node_local_env(package_module: str) -> str:
    return f"""
POSTGRES_USER=starter
POSTGRES_PASSWORD=starter
POSTGRES_DB=starter
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

MODEL_RUNNER_NODE_HOST=model-orchestrator
MODEL_RUNNER_NODE_PORT=9091
MODEL_RUNNER_TIMEOUT_SECONDS=60

CRUNCH_ID=starter-challenge
MODEL_BASE_CLASSNAME={package_module}.tracker.TrackerBase
CHECKPOINT_INTERVAL_SECONDS=60
"""


def _node_config_readme() -> str:
    return """
# config

- `callables.env`: dotted callable paths wired by workers
- `scheduled_prediction_configs.json`: challenge prediction schedule/scope defaults
"""


def _node_callables_env(package_module: str) -> str:
    return f"""
INFERENCE_INPUT_BUILDER={package_module}.inference:build_input
INFERENCE_OUTPUT_VALIDATOR={package_module}.validation:validate_output
SCORING_FUNCTION={package_module}.scoring:score_prediction
MODEL_SCORE_AGGREGATOR={package_module}.scoring:aggregate_model_scores
REPORT_SCHEMA_PROVIDER={package_module}.reporting:report_schema

LEADERBOARD_RANKER=node_template.extensions.default_callables:default_rank_leaderboard
RAW_INPUT_PROVIDER=node_template.extensions.default_callables:default_provide_raw_input
GROUND_TRUTH_RESOLVER=node_template.extensions.default_callables:default_resolve_ground_truth
PREDICTION_SCOPE_BUILDER=node_template.extensions.default_callables:default_build_prediction_scope
PREDICT_CALL_BUILDER=node_template.extensions.default_callables:default_build_predict_call
"""


def _scheduled_prediction_configs() -> str:
    payload = [
        {
            "scope_key": "default",
            "scope_template": {"asset": "BTC", "horizon_seconds": 60, "step_seconds": 60},
            "schedule": {"every_seconds": 60},
            "active": True,
            "order": 0,
        }
    ]
    return json.dumps(payload, indent=2)


def _node_deployment_readme() -> str:
    return """
# deployment

Place compose files and local runtime deployment assets here.

Start from the starter compose setup and only customize what your challenge needs.
"""


def _challenge_readme(name: str, package_module: str) -> str:
    return f"""
# crunch-{name}

Public challenge package.

Primary package: `{package_module}`

Implement required challenge callables in:

- `inference.py`
- `validation.py`
- `scoring.py`
- `reporting.py`
"""


def _challenge_pyproject(challenge_name: str, package_module: str) -> str:
    return f"""
[build-system]
requires = ["hatchling>=1.24"]
build-backend = "hatchling.build"

[project]
name = "{challenge_name}"
version = "0.1.0"
description = "Challenge package"
readme = "README.md"
requires-python = ">=3.12,<3.13"
dependencies = []

[tool.hatch.build.targets.wheel]
packages = ["{package_module}"]
"""


def _challenge_init() -> str:
    return """
from .tracker import TrackerBase

__all__ = ["TrackerBase"]
"""


def _challenge_tracker() -> str:
    return """
from __future__ import annotations


class TrackerBase:
    \"\"\"Base class for participant models.\"\"\"

    def tick(self, data: dict) -> None:
        self._latest_data = data

    def predict(self, **kwargs):
        raise NotImplementedError("Implement predict() in challenge quickstarters/models")
"""


def _challenge_inference() -> str:
    return """
from __future__ import annotations


def build_input(raw_input):
    return raw_input
"""


def _challenge_validation() -> str:
    return """
from __future__ import annotations


def validate_output(inference_output):
    if inference_output is None:
        raise ValueError("inference_output cannot be None")
    return inference_output
"""


def _challenge_scoring() -> str:
    return """
from __future__ import annotations


def score_prediction(prediction, ground_truth):
    return {"score": 0.0, "payload": {"reason": "replace with challenge score"}}


def aggregate_model_scores(scored_predictions, models):
    entries = []
    for model in models:
        entries.append(
            {
                "model_id": model.id,
                "model_name": model.name,
                "cruncher_name": model.player_name,
                "score": {
                    "metrics": {"recent": 0.0, "steady": 0.0, "anchor": 0.0},
                    "ranking": {"key": "anchor", "direction": "desc", "value": 0.0},
                    "payload": {},
                },
            }
        )
    return entries
"""


def _challenge_reporting() -> str:
    return """
from __future__ import annotations


def report_schema():
    return {
        "schema_version": "1",
        "leaderboard_columns": [
            {"key": "rank", "label": "Rank"},
            {"key": "model_name", "label": "Model"},
            {"key": "score_anchor", "label": "Anchor"},
        ],
        "metrics_widgets": [
            {"key": "score_anchor", "label": "Anchor", "series": ["score_anchor"]},
        ],
    }
"""


def _schemas_readme() -> str:
    return """
# schemas

Define challenge-specific JSONB payload models here.

Keep core envelope contracts in `coordinator_core` and embed challenge payloads inside them.
"""


def _plugins_readme(scope: str) -> str:
    if scope == "node":
        return """
# plugins

Node-side adapters/integrations/helpers.

Use this folder for wiring that should stay private to node infrastructure.
"""
    return """
# plugins

Challenge-side public adapters/helpers.

Use this folder for reusable public challenge code.
"""


def _extensions_readme(scope: str) -> str:
    if scope == "node":
        return """
# extensions

Node-side callable wiring and optional override hooks.

Use this folder for custom integration glue while keeping runtime core in `coordinator_core`.
"""
    return """
# extensions

Challenge-side callable groups and extension helpers.

Keep public scoring/ranking/reporting extension sets here when useful.
"""
