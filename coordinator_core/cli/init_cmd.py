from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coordinator_core.cli.presets import get_preset, list_preset_summaries
from coordinator_core.cli.scaffold_render import ensure_no_legacy_references, render_template_strict

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SUPPORTED_SPEC_VERSION = "1"

_CALLABLE_ORDER = [
    "INFERENCE_INPUT_BUILDER",
    "INFERENCE_OUTPUT_VALIDATOR",
    "SCORING_FUNCTION",
    "MODEL_SCORE_AGGREGATOR",
    "REPORT_SCHEMA_PROVIDER",
    "LEADERBOARD_RANKER",
    "RAW_INPUT_PROVIDER",
    "GROUND_TRUTH_RESOLVER",
    "PREDICTION_SCOPE_BUILDER",
    "PREDICT_CALL_BUILDER",
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
    preset: str
    callables: dict[str, str]
    scheduled_prediction_configs: list[dict[str, Any]]
    spec: dict[str, Any]


def is_valid_slug(name: str) -> bool:
    return bool(_SLUG_PATTERN.fullmatch(name or ""))


def load_spec(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Spec file not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Spec file is not valid JSON: {path} ({exc})") from exc

    if not isinstance(payload, dict):
        raise ValueError("Spec root must be a JSON object")

    return payload


def resolve_init_config(
    name: str | None,
    spec: dict[str, Any],
    require_spec_version: bool = False,
    preset_name: str | None = None,
) -> InitConfig:
    spec_name = spec.get("name")

    if require_spec_version:
        if "spec_version" not in spec:
            raise ValueError(
                f"Spec missing required 'spec_version'. Supported version: '{SUPPORTED_SPEC_VERSION}'."
            )
        if str(spec.get("spec_version")) != SUPPORTED_SPEC_VERSION:
            raise ValueError(
                "Unsupported spec_version "
                f"'{spec.get('spec_version')}'. Supported version: '{SUPPORTED_SPEC_VERSION}'."
            )

    if name and spec_name and name != spec_name:
        raise ValueError(
            f"Name mismatch: CLI name '{name}' does not match spec name '{spec_name}'."
        )

    resolved_name = str(name or spec_name or "")
    if not resolved_name:
        raise ValueError("Challenge name required. Provide <name> or include 'name' in --spec.")

    if not is_valid_slug(resolved_name):
        raise ValueError(
            "Invalid challenge name. Use lowercase slug format like 'btc-trader' "
            "(letters, numbers, single dashes)."
        )

    package_module = f"crunch_{resolved_name.replace('-', '_')}"
    node_name = f"crunch-node-{resolved_name}"
    challenge_name = f"crunch-{resolved_name}"

    selected_preset = str(preset_name or spec.get("preset") or "baseline")
    preset = get_preset(selected_preset)
    normalized_spec = dict(spec)
    normalized_spec["preset"] = selected_preset

    crunch_id = str(spec.get("crunch_id", "starter-challenge"))
    model_base_classname = _normalize_model_base_classname(
        str(spec.get("model_base_classname", "tracker.TrackerBase")),
        package_module=package_module,
    )
    normalized_spec["model_base_classname"] = model_base_classname

    checkpoint_interval_seconds = int(
        spec.get("checkpoint_interval_seconds", preset.get("checkpoint_interval_seconds", 60))
    )
    if checkpoint_interval_seconds <= 0:
        raise ValueError("checkpoint_interval_seconds must be > 0")

    callables = _merge_callables(
        package_module=package_module,
        defaults=preset.get("callables") or {},
        overrides=spec.get("callables") or {},
    )
    scheduled_prediction_configs = _resolve_scheduled_prediction_configs(
        value=spec.get("scheduled_prediction_configs"),
        default_value=preset.get("scheduled_prediction_configs"),
    )

    return InitConfig(
        name=resolved_name,
        package_module=package_module,
        node_name=node_name,
        challenge_name=challenge_name,
        crunch_id=crunch_id,
        model_base_classname=model_base_classname,
        checkpoint_interval_seconds=checkpoint_interval_seconds,
        preset=selected_preset,
        callables=callables,
        scheduled_prediction_configs=scheduled_prediction_configs,
        spec=normalized_spec,
    )


def _normalize_model_base_classname(value: str, package_module: str) -> str:
    canonical = "tracker.TrackerBase"
    if not value:
        return canonical

    if value in (canonical, f"{package_module}.tracker.TrackerBase"):
        return canonical

    return value


def run_init(
    name: str | None,
    project_root: Path,
    force: bool = False,
    spec_path: Path | None = None,
    preset_name: str | None = None,
    list_presets: bool = False,
) -> int:
    if list_presets:
        print("Available presets:")
        for preset, description in list_preset_summaries():
            print(f"- {preset}: {description}")
        return 0

    try:
        spec = load_spec(spec_path) if spec_path is not None else {}
        config = resolve_init_config(
            name=name,
            spec=spec,
            require_spec_version=spec_path is not None,
            preset_name=preset_name,
        )
    except ValueError as exc:
        print(str(exc))
        return 1

    workspace_dir = project_root / config.name
    if workspace_dir.exists():
        if not force:
            print(f"Target already exists: {workspace_dir}. Use --force to overwrite.")
            return 1
        shutil.rmtree(workspace_dir)

    try:
        files = _render_scaffold_files(config=config, include_spec=spec_path is not None)
    except ValueError as exc:
        print(str(exc))
        return 1

    _write_tree(workspace_dir, files)
    try:
        _vendor_runtime_packages(workspace_dir / config.node_name / "runtime")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to vendor runtime packages: {exc}")
        return 1

    print(f"Scaffold created: {workspace_dir}")
    print(f"Next: cd {workspace_dir / config.node_name}")
    return 0


def _merge_callables(
    package_module: str,
    defaults: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, str]:
    if not isinstance(defaults, dict) or not defaults:
        raise ValueError("Preset callables must be a non-empty object")
    if not isinstance(overrides, dict):
        raise ValueError("'callables' must be an object of ENV_KEY -> module:callable")

    rendered_defaults: dict[str, str] = {}
    for key in _CALLABLE_ORDER:
        if key not in defaults:
            raise ValueError(f"Preset callables missing required key '{key}'")

        value = defaults[key]
        if not isinstance(value, str):
            raise ValueError(f"Preset callable for '{key}' must be '<module>:<callable>'")
        rendered_defaults[key] = value.format(package_module=package_module)

    merged = dict(rendered_defaults)
    for key, value in overrides.items():
        if key not in rendered_defaults:
            allowed = ", ".join(sorted(rendered_defaults.keys()))
            raise ValueError(f"Unknown callable key '{key}'. Allowed keys: {allowed}")
        if not isinstance(value, str) or ":" not in value:
            raise ValueError(f"Callable override for '{key}' must be '<module>:<callable>'")
        merged[key] = value

    for key, value in merged.items():
        _validate_callable_path(key=key, value=value)

    return merged


def _validate_callable_path(key: str, value: str) -> None:
    module_path, sep, callable_name = value.partition(":")
    if not sep or not module_path or not callable_name:
        raise ValueError(f"Callable override for '{key}' must be '<module>:<callable>'")

    if module_path.startswith("node_template"):
        raise ValueError(
            f"Callable '{key}' uses internal module path '{module_path}'. "
            "Use coordinator_runtime.* or challenge/node-local module paths instead."
        )


def _resolve_scheduled_prediction_configs(value: Any, default_value: Any) -> list[dict[str, Any]]:
    resolved = value if value is not None else default_value

    if not isinstance(resolved, list) or not resolved:
        raise ValueError("'scheduled_prediction_configs' must be a non-empty array")

    for idx, row in enumerate(resolved):
        if not isinstance(row, dict):
            raise ValueError(f"scheduled_prediction_configs[{idx}] must be an object")
        for field in ("scope_key", "scope_template", "schedule"):
            if field not in row:
                raise ValueError(f"scheduled_prediction_configs[{idx}] missing '{field}'")

    return resolved


def _render_scaffold_files(config: InitConfig, include_spec: bool) -> dict[str, str]:
    local_env = _node_local_env(
        crunch_id=config.crunch_id,
        base_classname=config.model_base_classname,
        checkpoint_interval_seconds=config.checkpoint_interval_seconds,
        callables=config.callables,
    )

    path_values = {
        "node_name": config.node_name,
        "challenge_name": config.challenge_name,
        "package_module": config.package_module,
    }

    manifest: list[tuple[str, str]] = [
        ("README.md", _workspace_readme(config.name)),
        ("{node_name}/README.md", _node_readme(config.name)),
        ("{node_name}/Makefile", _node_makefile()),
        ("{node_name}/pyproject.toml", _node_pyproject(config.node_name, config.challenge_name)),
        ("{node_name}/Dockerfile", _node_dockerfile()),
        ("{node_name}/docker-compose.yml", _node_compose(config.node_name, config.challenge_name)),
        ("{node_name}/scripts/verify_e2e.py", _node_verify_e2e_script()),
        ("{node_name}/.local.env", local_env),
        ("{node_name}/.local.env.example", local_env),
        ("{node_name}/config/README.md", _node_config_readme()),
        ("{node_name}/config/callables.env", _node_callables_env(config.callables)),
        (
            "{node_name}/config/scheduled_prediction_configs.json",
            _scheduled_prediction_configs(config.scheduled_prediction_configs),
        ),
        ("{node_name}/deployment/README.md", _node_deployment_readme()),
        (
            "{node_name}/deployment/model-orchestrator-local/config/docker-entrypoint.sh",
            _orchestrator_entrypoint_script(),
        ),
        (
            "{node_name}/deployment/model-orchestrator-local/config/orchestrator.dev.yml",
            _orchestrator_dev_config(config.crunch_id),
        ),
        (
            "{node_name}/deployment/model-orchestrator-local/config/models.dev.yml",
            _orchestrator_models_dev(config.crunch_id),
        ),
        (
            "{node_name}/deployment/model-orchestrator-local/config/starter-submission/main.py",
            _starter_submission_main(),
        ),
        (
            "{node_name}/deployment/model-orchestrator-local/config/starter-submission/tracker.py",
            _starter_submission_tracker(),
        ),
        (
            "{node_name}/deployment/model-orchestrator-local/config/starter-submission/requirements.txt",
            _starter_submission_requirements(),
        ),
        (
            "{node_name}/deployment/model-orchestrator-local/data/.gitkeep",
            "",
        ),
        (
            "{node_name}/deployment/report-ui/config/global-settings.json",
            _report_ui_global_settings(config.node_name),
        ),
        (
            "{node_name}/deployment/report-ui/config/leaderboard-columns.json",
            _report_ui_leaderboard_columns(),
        ),
        (
            "{node_name}/deployment/report-ui/config/metrics-widgets.json",
            _report_ui_metrics_widgets(),
        ),
        ("{node_name}/plugins/README.md", _plugins_readme("node")),
        ("{node_name}/extensions/README.md", _extensions_readme("node")),
        ("{challenge_name}/README.md", _challenge_readme(config.name, config.package_module)),
        (
            "{challenge_name}/pyproject.toml",
            _challenge_pyproject(config.challenge_name, config.package_module),
        ),
        ("{challenge_name}/{package_module}/__init__.py", _challenge_init()),
        ("{challenge_name}/{package_module}/tracker.py", _challenge_tracker()),
        ("{challenge_name}/{package_module}/inference.py", _challenge_inference()),
        ("{challenge_name}/{package_module}/validation.py", _challenge_validation()),
        ("{challenge_name}/{package_module}/scoring.py", _challenge_scoring()),
        ("{challenge_name}/{package_module}/reporting.py", _challenge_reporting()),
        ("{challenge_name}/{package_module}/schemas/README.md", _schemas_readme()),
        ("{challenge_name}/{package_module}/plugins/README.md", _plugins_readme("challenge")),
        (
            "{challenge_name}/{package_module}/extensions/README.md",
            _extensions_readme("challenge"),
        ),
    ]

    if include_spec:
        manifest.append(("spec.json", json.dumps(config.spec, indent=2)))

    files = {
        render_template_strict(path_template, path_values): content
        for path_template, content in manifest
    }

    ensure_no_legacy_references(files)
    return files


def _write_tree(base_dir: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = base_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")


def _vendor_runtime_packages(target_runtime_dir: Path) -> None:
    import coordinator_core
    import coordinator_runtime
    import node_template

    package_roots = {
        "coordinator_core": Path(coordinator_core.__file__).resolve().parent,
        "coordinator_runtime": Path(coordinator_runtime.__file__).resolve().parent,
        "node_template": Path(node_template.__file__).resolve().parent,
    }

    target_runtime_dir.mkdir(parents=True, exist_ok=True)
    for package_name, source_dir in package_roots.items():
        destination = target_runtime_dir / package_name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source_dir, destination)


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

Standalone node runtime workspace for `{name}`.

## What belongs here

- local deployment/runtime config (`docker-compose.yml`, `Dockerfile`, `.local.env`)
- callable path configuration (`config/callables.env`)
- node-private adapters (`plugins/`) and overrides (`extensions/`)
- vendored runtime packages under `runtime/`

This folder is self-contained and runnable without referencing a parent starter repo.

## Local run

From this folder:

```bash
make deploy
make verify-e2e
```
"""


def _node_pyproject(node_name: str, challenge_name: str) -> str:
    return f"""
[project]
name = "{node_name}"
version = "0.1.0"
description = "Standalone node workspace"
requires-python = ">=3.12,<3.13"
dependencies = [
  "{challenge_name}",
]

[tool.uv.sources]
{challenge_name} = {{ path = "../{challenge_name}", editable = true }}
"""


def _node_makefile() -> str:
    return """
COMPOSE := docker compose -f docker-compose.yml --env-file .local.env

.PHONY: deploy down logs verify-e2e

deploy:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

verify-e2e:
	uv run --with requests python scripts/verify_e2e.py
"""


def _node_dockerfile() -> str:
    return """
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    densitypdf>=0.1.4 \
    fastapi>=0.121.3 \
    model-runner-client>=0.10.0 \
    numpy>=2.3.4 \
    psycopg2-binary>=2.9.11 \
    requests>=2.32.5 \
    sqlmodel>=0.0.27 \
    uvicorn>=0.38.0

COPY runtime/coordinator_core ./coordinator_core
COPY runtime/coordinator_runtime ./coordinator_runtime
COPY runtime/node_template ./node_template

CMD ["python", "-m", "node_template"]
"""


def _node_compose(node_name: str, challenge_name: str) -> str:
    network_name = f"{node_name}-net"
    return f"""
services:
  postgres:
    image: postgres:15
    container_name: {node_name}-postgres
    restart: always
    ports:
      - "5432:5432"
    environment:
      POSTGRES_HOST: ${{POSTGRES_HOST:-postgres}}
      POSTGRES_PORT: ${{POSTGRES_PORT:-5432}}
      POSTGRES_USER: ${{POSTGRES_USER:-starter}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-starter}}
      POSTGRES_DB: ${{POSTGRES_DB:-starter}}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -d ${{POSTGRES_DB:-starter}} -U ${{POSTGRES_USER:-starter}}"]
      interval: 2s
      timeout: 5s
      retries: 20
      start_period: 10s
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks: [coordinator-net]

  init-db:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: {node_name}-init-db
    command: ["python", "-m", "node_template.infrastructure.db.init_db"]
    environment:
      POSTGRES_HOST: ${{POSTGRES_HOST:-postgres}}
      POSTGRES_PORT: ${{POSTGRES_PORT:-5432}}
      POSTGRES_USER: ${{POSTGRES_USER:-starter}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-starter}}
      POSTGRES_DB: ${{POSTGRES_DB:-starter}}
      SCHEDULED_PREDICTION_CONFIGS_PATH: /app/config/scheduled_prediction_configs.json
    volumes:
      - ./config/scheduled_prediction_configs.json:/app/config/scheduled_prediction_configs.json:ro
    depends_on:
      postgres:
        condition: service_healthy
    networks: [coordinator-net]

  predict-worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: {node_name}-predict-worker
    restart: always
    command: ["python", "-m", "node_template.workers.predict_worker"]
    environment:
      POSTGRES_HOST: ${{POSTGRES_HOST:-postgres}}
      POSTGRES_PORT: ${{POSTGRES_PORT:-5432}}
      POSTGRES_USER: ${{POSTGRES_USER:-starter}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-starter}}
      POSTGRES_DB: ${{POSTGRES_DB:-starter}}
      MODEL_RUNNER_NODE_HOST: ${{MODEL_RUNNER_NODE_HOST:-model-orchestrator}}
      MODEL_RUNNER_NODE_PORT: ${{MODEL_RUNNER_NODE_PORT:-9091}}
      MODEL_RUNNER_TIMEOUT_SECONDS: ${{MODEL_RUNNER_TIMEOUT_SECONDS:-60}}
      CHECKPOINT_INTERVAL_SECONDS: ${{CHECKPOINT_INTERVAL_SECONDS:-60}}
      CRUNCH_ID: ${{CRUNCH_ID:-starter-challenge}}
      MODEL_BASE_CLASSNAME: ${{MODEL_BASE_CLASSNAME:-tracker.TrackerBase}}
      INFERENCE_INPUT_BUILDER: ${{INFERENCE_INPUT_BUILDER}}
      INFERENCE_OUTPUT_VALIDATOR: ${{INFERENCE_OUTPUT_VALIDATOR}}
      RAW_INPUT_PROVIDER: ${{RAW_INPUT_PROVIDER}}
      PREDICTION_SCOPE_BUILDER: ${{PREDICTION_SCOPE_BUILDER}}
      PREDICT_CALL_BUILDER: ${{PREDICT_CALL_BUILDER}}
      PYTHONPATH: /app/challenge
    volumes:
      - ../{challenge_name}:/app/challenge
    depends_on:
      init-db:
        condition: service_completed_successfully
      model-orchestrator:
        condition: service_started
    networks: [coordinator-net]

  score-worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: {node_name}-score-worker
    restart: always
    command: ["python", "-m", "node_template.workers.score_worker"]
    environment:
      POSTGRES_HOST: ${{POSTGRES_HOST:-postgres}}
      POSTGRES_PORT: ${{POSTGRES_PORT:-5432}}
      POSTGRES_USER: ${{POSTGRES_USER:-starter}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-starter}}
      POSTGRES_DB: ${{POSTGRES_DB:-starter}}
      CHECKPOINT_INTERVAL_SECONDS: ${{CHECKPOINT_INTERVAL_SECONDS:-60}}
      SCORING_FUNCTION: ${{SCORING_FUNCTION}}
      MODEL_SCORE_AGGREGATOR: ${{MODEL_SCORE_AGGREGATOR}}
      LEADERBOARD_RANKER: ${{LEADERBOARD_RANKER}}
      GROUND_TRUTH_RESOLVER: ${{GROUND_TRUTH_RESOLVER}}
      PYTHONPATH: /app/challenge
    volumes:
      - ../{challenge_name}:/app/challenge
    depends_on:
      init-db:
        condition: service_completed_successfully
    networks: [coordinator-net]

  report-worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: {node_name}-report-worker
    restart: always
    command: ["python", "-m", "node_template.workers.report_worker"]
    ports:
      - "8000:8000"
    environment:
      POSTGRES_HOST: ${{POSTGRES_HOST:-postgres}}
      POSTGRES_PORT: ${{POSTGRES_PORT:-5432}}
      POSTGRES_USER: ${{POSTGRES_USER:-starter}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-starter}}
      POSTGRES_DB: ${{POSTGRES_DB:-starter}}
      REPORT_SCHEMA_PROVIDER: ${{REPORT_SCHEMA_PROVIDER}}
      PYTHONPATH: /app/challenge
    volumes:
      - ../{challenge_name}:/app/challenge
    depends_on:
      init-db:
        condition: service_completed_successfully
    networks: [coordinator-net]

  model-orchestrator:
    build:
      context: https://github.com/crunchdao/model-orchestrator.git
    container_name: {node_name}-model-orchestrator
    restart: unless-stopped
    init: true
    ports:
      - "9091:9091"
    environment:
      DOCKER_NETWORK_NAME: {network_name}
    volumes:
      - ./deployment/model-orchestrator-local/data:/app/data
      - ./deployment/model-orchestrator-local/config:/app/config
      - /var/run/docker.sock:/var/run/docker.sock
    privileged: true
    entrypoint: ["sh", "/app/config/docker-entrypoint.sh"]
    command:
      [
        "model-orchestrator",
        "dev",
        "--configuration-file",
        "/app/config/orchestrator.dev.yml",
        "--rebuild",
        "if-code-modified",
      ]
    networks: [coordinator-net]

  report-ui:
    build:
      context: https://github.com/crunchdao/coordinator-webapp.git
      dockerfile: apps/starter/Dockerfile
      args:
        NEXT_PUBLIC_API_URL: "http://report-worker:8000"
        NEXT_PUBLIC_API_URL_MODEL_ORCHESTRATOR: "http://model-orchestrator:8001"
    container_name: {node_name}-report-ui
    ports:
      - "3000:3000"
    volumes:
      - ./deployment/report-ui/config:/app/config
      - ./deployment/report-ui/config:/app/apps/starter/config
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on:
      - report-worker
    networks: [coordinator-net]

networks:
  coordinator-net:
    driver: bridge
    name: {network_name}

volumes:
  postgres-data:
"""


def _node_verify_e2e_script() -> str:
    return """
from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timedelta, timezone

import requests


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _get_json(base_url: str, path: str, params: dict | None = None):
    response = requests.get(f"{base_url}{path}", params=params, timeout=5)
    response.raise_for_status()
    return response.json()


def _detect_model_runner_failure(log_text: str) -> str | None:
    markers = ["BAD_IMPLEMENTATION", "No Inherited class found", "Import error occurred"]
    for line in log_text.splitlines():
        if any(marker in line for marker in markers):
            return line.strip()
    return None


def _read_model_orchestrator_logs() -> str:
    cmd = [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "--env-file",
        ".local.env",
        "logs",
        "model-orchestrator",
        "--tail",
        "300",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return (result.stdout or "") + "\\n" + (result.stderr or "")


def main() -> int:
    base_url = os.getenv("REPORT_API_URL", "http://localhost:8000")
    timeout_seconds = int(os.getenv("E2E_VERIFY_TIMEOUT_SECONDS", "240"))
    poll_seconds = int(os.getenv("E2E_VERIFY_POLL_SECONDS", "5"))

    print(f"[verify-e2e] base_url={base_url} timeout={timeout_seconds}s")

    deadline = time.time() + timeout_seconds
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    last_error: str | None = None

    while time.time() < deadline:
        try:
            model_logs = _read_model_orchestrator_logs()
            failure = _detect_model_runner_failure(model_logs)
            if failure is not None:
                raise RuntimeError(f"model-runner failure detected: {failure}")

            health = _get_json(base_url, "/healthz")
            if health.get("status") != "ok":
                raise RuntimeError(f"healthcheck not ok: {health}")

            models = _get_json(base_url, "/reports/models")
            if not models:
                raise RuntimeError("no models registered yet")

            model_id = models[0]["model_id"]
            now = datetime.now(timezone.utc)
            predictions = _get_json(
                base_url,
                "/reports/predictions",
                params={
                    "projectIds": model_id,
                    "start": _iso(since),
                    "end": _iso(now),
                },
            )
            leaderboard = _get_json(base_url, "/reports/leaderboard")

            scored = [
                row
                for row in predictions
                if row.get("score_value") is not None and row.get("score_failed") is False
            ]
            if scored and leaderboard:
                print(
                    "[verify-e2e] success "
                    f"models={len(models)} scored_predictions={len(scored)} leaderboard_entries={len(leaderboard)}"
                )
                return 0

            raise RuntimeError(
                f"waiting for scored predictions/leaderboard (predictions={len(predictions)} leaderboard={len(leaderboard)})"
            )
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            print(f"[verify-e2e] waiting: {last_error}")
            time.sleep(poll_seconds)

    print(f"[verify-e2e] FAILED: timeout reached. last_error={last_error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
"""


def _node_local_env(
    crunch_id: str,
    base_classname: str,
    checkpoint_interval_seconds: int,
    callables: dict[str, str],
) -> str:
    callables_block = _node_callables_env(callables)

    return f"""
POSTGRES_USER=starter
POSTGRES_PASSWORD=starter
POSTGRES_DB=starter
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

MODEL_RUNNER_NODE_HOST=model-orchestrator
MODEL_RUNNER_NODE_PORT=9091
MODEL_RUNNER_TIMEOUT_SECONDS=60

CRUNCH_ID={crunch_id}
MODEL_BASE_CLASSNAME={base_classname}
CHECKPOINT_INTERVAL_SECONDS={checkpoint_interval_seconds}

{callables_block}
"""


def _node_config_readme() -> str:
    return """
# config

- `callables.env`: dotted callable paths wired by workers
- `scheduled_prediction_configs.json`: challenge prediction schedule/scope defaults
"""


def _node_callables_env(callables: dict[str, str]) -> str:
    return "\n".join(f"{key}={callables[key]}" for key in _CALLABLE_ORDER)


def _scheduled_prediction_configs(payload: list[dict[str, Any]]) -> str:
    return json.dumps(payload, indent=2)


def _node_deployment_readme() -> str:
    return """
# deployment

Local deployment assets for this standalone node workspace.

- `model-orchestrator-local/config`: local model-orchestrator configuration and starter submission
- `report-ui/config`: report UI local settings
"""


def _orchestrator_entrypoint_script() -> str:
    return """
#!/bin/sh
set -e

bootstrap_submission() {
  submission_id="$1"
  template_dir="$2"
  submission_dir="/app/data/submissions/${submission_id}"

  if [ ! -f "${submission_dir}/main.py" ] || [ ! -f "${submission_dir}/tracker.py" ]; then
    echo "Bootstrapping local starter submission files into ${submission_dir}"
    mkdir -p "${submission_dir}"
    cp -f "${template_dir}"/* "${submission_dir}"/
  fi
}

bootstrap_submission "starter-submission" "/app/config/starter-submission"

exec "$@"
"""


def _orchestrator_dev_config(crunch_id: str) -> str:
    return f"""
logging:
  level: debug

infrastructure:
  database:
    type: sqlite
    path: "/app/data/orchestrator.dev.db"

  publishers:
    - type: websocket
      address: "0.0.0.0"
      port: 9091

  runner:
    type: local
    docker-network-name: "${{DOCKER_NETWORK_NAME}}"
    submission-storage-path-format: "/app/data/submissions/{{id}}"
    resource-storage-path-format: "/app/data/models/{{id}}"

watcher:
  interval: 1
  poller:
    type: yaml
    path: "/app/config/models.dev.yml"

crunches:
  - id: "{crunch_id}"
    name: "{crunch_id}"
    infrastructure:
      zone: "local"

can-place-in-quarantine: false
use-augmented-info: false
"""


def _orchestrator_models_dev(crunch_id: str) -> str:
    return f"""
models:
  - id: "1"
    submission_id: starter-submission
    crunch_id: {crunch_id}
    desired_state: RUNNING
    model_name: starter-model
    cruncher_name: local-dev
    cruncher_id: local-0001
"""


def _starter_submission_main() -> str:
    return """
from __future__ import annotations

from tracker import TrackerBase


class LocalStarterSubmission(TrackerBase):
    def predict(self, asset: str, horizon: int, step: int):
        return {"score": 0.5}
"""


def _starter_submission_tracker() -> str:
    return """
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TrackerBase:
    history: dict[str, list[tuple[int, float]]] = field(default_factory=lambda: defaultdict(list))

    def tick(self, data: dict[str, list[tuple[int, float]]]) -> None:
        for asset, points in (data or {}).items():
            self.history.setdefault(asset, []).extend(points or [])

    def predict(self, asset: str, horizon: int, step: int):
        raise NotImplementedError
"""


def _starter_submission_requirements() -> str:
    return """
# Add optional model dependencies here for local model-orchestrator runs.
"""


def _report_ui_global_settings(node_name: str) -> str:
    payload = {
        "endpoints": {"leaderboard": "/reports/leaderboard"},
        "logs": {
            "containerNames": [
                f"{node_name}-score-worker",
                f"{node_name}-predict-worker",
                f"{node_name}-report-worker",
                f"{node_name}-model-orchestrator",
            ]
        },
    }
    return json.dumps(payload, indent=2)


def _report_ui_leaderboard_columns() -> str:
    payload = [
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
            "property": "score_recent",
            "format": "decimal-1",
            "displayName": "Recent Score",
            "tooltip": "The score of the player over the last 24 hours.",
            "nativeConfiguration": None,
            "order": 20,
        },
        {
            "id": 3,
            "type": "VALUE",
            "property": "score_steady",
            "format": "decimal-2",
            "displayName": "Steady Score",
            "tooltip": "The score of the player over the last 72 hours.",
            "nativeConfiguration": None,
            "order": 30,
        },
        {
            "id": 4,
            "type": "VALUE",
            "property": "score_anchor",
            "format": "decimal-3",
            "displayName": "Anchor Score",
            "tooltip": "The score of the player over the last 7 days.",
            "nativeConfiguration": None,
            "order": 40,
        },
    ]
    return json.dumps(payload, indent=2)


def _report_ui_metrics_widgets() -> str:
    payload = [
        {
            "id": 1,
            "type": "CHART",
            "displayName": "Score Metrics",
            "tooltip": None,
            "order": 10,
            "endpointUrl": "/reports/models/global",
            "nativeConfiguration": {
                "type": "line",
                "xAxis": {"name": "performed_at"},
                "yAxis": {
                    "series": [
                        {"name": "score_recent", "label": "Recent Score"},
                        {"name": "score_steady", "label": "Steady Score"},
                        {"name": "score_anchor", "label": "Anchor Score"},
                    ],
                    "format": "decimal-2",
                },
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
                "yAxis": {
                    "series": [{"name": "score_value"}],
                    "format": "decimal-2",
                },
                "alertConfig": {"reasonField": "score_failed_reason", "field": "score_success"},
                "filterConfig": [
                    {"type": "select", "label": "Asset", "property": "asset", "autoSelectFirst": True},
                    {
                        "type": "select",
                        "label": "Horizon",
                        "property": "horizon",
                        "autoSelectFirst": True,
                    },
                ],
                "groupByProperty": "param",
                "displayEvolution": False,
            },
        },
        {
            "id": 3,
            "type": "CHART",
            "displayName": "Rolling score by parameters",
            "tooltip": None,
            "order": 20,
            "endpointUrl": "/reports/models/params",
            "nativeConfiguration": {
                "type": "line",
                "xAxis": {"name": "performed_at"},
                "yAxis": {
                    "series": [
                        {"name": "score_recent", "label": "Recent Score"},
                        {"name": "score_steady", "label": "Steady Score"},
                        {"name": "score_anchor", "label": "Anchor Score"},
                    ],
                    "format": "decimal:2",
                },
                "filterConfig": [
                    {"type": "select", "label": "Asset", "property": "asset", "autoSelectFirst": True},
                    {
                        "type": "select",
                        "label": "Horizon",
                        "property": "horizon",
                        "autoSelectFirst": True,
                    },
                ],
                "groupByProperty": "param",
                "displayEvolution": False,
            },
        },
    ]
    return json.dumps(payload, indent=2)


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
    # Replace with challenge-specific score computation.
    return {"value": 0.0, "success": True, "failed_reason": None}


def aggregate_model_scores(scored_predictions, models):
    # Optional challenge-specific aggregator. Default runtime wiring uses
    # the coordinator runtime's built-in model-score aggregation unless
    # overridden in spec.
    entries = []
    for model in models.values():
        entries.append(
            {
                "model_id": model.id,
                "model_name": model.name,
                "cruncher_name": model.player_name,
                "score": {
                    "metrics": {"average": 0.0},
                    "ranking": {"key": "average", "direction": "desc", "value": 0.0},
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
# plugins (node-private)

Use this folder for **node-side integrations** that should not live in the public challenge package.

## Put code here when

- you call private/external APIs (keys/secrets live in node env)
- you need infrastructure-specific data shaping
- logic is operational, not challenge-contract logic

## Typical modules

- `raw_input.py` → source data adapters
- `ground_truth.py` → truth resolvers

## Expected callable shapes

```python
def provide_raw_input(now):
    ...

def resolve_ground_truth(prediction):
    ...  # return dict or None
```

## Wire via env

- `RAW_INPUT_PROVIDER=node_plugins.raw_input:provide_raw_input`
- `GROUND_TRUTH_RESOLVER=node_plugins.ground_truth:resolve_ground_truth`

Keep these functions pure and deterministic where possible.
"""
    return """
# plugins (challenge-public)

Use this folder for **reusable public helpers/adapters** that support challenge logic.

## Put code here when

- helper is useful across inference/scoring/reporting
- code is safe to publish (no secrets)
- it does not depend on private node infrastructure

## Typical modules

- `features.py` → feature engineering helpers
- `math_utils.py` → shared scoring math
- `normalization.py` → shared transforms

Then import from `inference.py`, `scoring.py`, or `reporting.py`.
"""


def _extensions_readme(scope: str) -> str:
    if scope == "node":
        return """
# extensions (node-private)

Use this folder for **node-specific callable overrides** selected via env variables.

## Put code here when

- default functionality from the coordinator core packages is not enough
- override should stay private to this node deployment
- you need custom ranking/scope/predict/report behavior

## Common override callables

```python
def build_prediction_scope(config, inference_input):
    ...

def build_predict_call(config, inference_input, scope):
    ...

def rank_leaderboard(entries):
    ...
```

## Wire via env

- `PREDICTION_SCOPE_BUILDER=extensions.scope:build_prediction_scope`
- `PREDICT_CALL_BUILDER=extensions.predict:build_predict_call`
- `LEADERBOARD_RANKER=extensions.ranking:rank_leaderboard`

Match signatures exactly, otherwise runtime validation will fail.
"""
    return """
# extensions (challenge-public)

Use this folder to group **public challenge callable profiles**.

## Recommended structure

- `baseline.py` → default scoring/ranking/report schema
- `risk_adjusted.py` → alternative profile

## Example exports per profile

```python
def score_prediction(prediction, ground_truth):
    ...

def aggregate_model_scores(scored_predictions, models):
    ...

def report_schema():
    ...
```

Then point env vars to the selected profile module.
"""
