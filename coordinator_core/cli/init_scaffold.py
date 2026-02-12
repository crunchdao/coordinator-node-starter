from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coordinator_core.cli.init_config import InitConfig
from coordinator_core.cli.pack_templates import render_pack_templates
from coordinator_core.cli.scaffold_render import ensure_no_legacy_references, render_template_strict


def render_scaffold_files(config: InitConfig, include_spec: bool) -> dict[str, str]:
    local_env = node_local_env(
        crunch_id=config.crunch_id,
        base_classname=config.model_base_classname,
        checkpoint_interval_seconds=config.checkpoint_interval_seconds,
        callables=config.callables,
    )

    path_values = {
        "name": config.name,
        "node_name": config.node_name,
        "challenge_name": config.challenge_name,
        "package_module": config.package_module,
        "crunch_id": config.crunch_id,
    }

    template_files = render_pack_templates(config.template_set, path_values)

    manifest: list[tuple[str, str]] = [
        ("{node_name}/.local.env", local_env),
        ("{node_name}/.local.env.example", local_env),
        ("{node_name}/config/callables.env", runtime_definitions_env(config.callables)),
        (
            "{node_name}/config/scheduled_prediction_configs.json",
            scheduled_prediction_configs(config.scheduled_prediction_configs),
        ),
    ]

    if include_spec:
        manifest.append(("spec.json", json.dumps(config.spec, indent=2)))

    generated_files = {
        render_template_strict(path_template, path_values): content
        for path_template, content in manifest
    }

    files = {**template_files, **generated_files}

    ensure_no_legacy_references(files)
    return files


def write_tree(base_dir: Path, files: dict[str, str]) -> None:
    for relative_path, content in files.items():
        path = base_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")


def write_process_log(workspace_dir: Path, events: list[dict[str, Any]]) -> None:
    path = workspace_dir / "process-log.jsonl"
    lines: list[str] = []
    for event in events:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        lines.append(json.dumps(payload, separators=(",", ":")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def vendor_runtime_packages(target_runtime_dir: Path) -> None:
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


def scheduled_prediction_configs(payload: list[dict[str, Any]]) -> str:
    return json.dumps(payload, indent=2)


def runtime_definitions_env(callables: dict[str, str]) -> str:
    return "\n".join(f"{key}={value}" for key, value in sorted(callables.items()))


def node_local_env(
    crunch_id: str,
    base_classname: str,
    checkpoint_interval_seconds: int,
    callables: dict[str, str],
) -> str:
    callables_block = runtime_definitions_env(callables)

    return f"""
POSTGRES_USER=starter
POSTGRES_PASSWORD=starter
POSTGRES_DB=starter
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

MODEL_RUNNER_NODE_HOST=model-orchestrator
MODEL_RUNNER_NODE_PORT=9091
MODEL_RUNNER_TIMEOUT_SECONDS=60

# ── Web UI ──────────────────────────────────────────────────────────
# Default: starter (local dev dashboard)
# To graduate to the full platform UI, change to:
#   REPORT_UI_APP=platform
#   REPORT_UI_DOCKERFILE=apps/platform/Dockerfile
#   NEXT_PUBLIC_API_URL=https://hub.crunchdao.com
REPORT_UI_APP=starter
REPORT_UI_BUILD_CONTEXT=https://github.com/crunchdao/coordinator-webapp.git
REPORT_UI_DOCKERFILE=apps/starter/Dockerfile
# NEXT_PUBLIC_API_URL=http://report-worker:8000
# NEXT_PUBLIC_API_URL_MODEL_ORCHESTRATOR=http://model-orchestrator:8001

FEED_PROVIDER=pyth
FEED_ASSETS=BTC
FEED_KIND=tick
FEED_GRANULARITY=1s
FEED_POLL_SECONDS=5
FEED_BACKFILL_MINUTES=180
FEED_CANDLES_WINDOW=120
MARKET_RECORD_TTL_DAYS=90
MARKET_RETENTION_CHECK_SECONDS=3600

CRUNCH_ID={crunch_id}
MODEL_BASE_CLASSNAME={base_classname}
CHECKPOINT_INTERVAL_SECONDS={checkpoint_interval_seconds}

{callables_block}
"""
