from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coordinator_cli.commands.init_config import InitConfig
from coordinator_cli.commands.pack_templates import render_pack_templates
from coordinator_cli.commands.scaffold_render import ensure_no_legacy_references


def render_scaffold_files(config: InitConfig) -> dict[str, str]:
    path_values = {
        "name": config.name,
        "node_name": config.node_name,
        "challenge_name": config.challenge_name,
        "package_module": config.package_module,
        "crunch_id": config.crunch_id,
    }

    template_files = render_pack_templates("default", path_values)

    callables_env = "\n".join(f"{k}={v}" for k, v in sorted(config.callables.items()))
    schedule_json = json.dumps(config.scheduled_prediction_configs, indent=2)
    local_env = _build_local_env(config)

    generated: dict[str, str] = {
        f"{config.node_name}/.local.env": local_env,
        f"{config.node_name}/.local.env.example": local_env,
        f"{config.node_name}/config/callables.env": callables_env,
        f"{config.node_name}/config/scheduled_prediction_configs.json": schedule_json,
    }

    files = {**template_files, **generated}
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
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
        lines.append(json.dumps(payload, separators=(",", ":")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def vendor_runtime_packages(target_runtime_dir: Path) -> None:
    import coordinator

    source_dir = Path(coordinator.__file__).resolve().parent
    target_runtime_dir.mkdir(parents=True, exist_ok=True)
    destination = target_runtime_dir / "coordinator"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source_dir, destination)


def _build_local_env(config: InitConfig) -> str:
    callables_block = "\n".join(f"{k}={v}" for k, v in sorted(config.callables.items()))

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
REPORT_UI_APP=starter
REPORT_UI_BUILD_CONTEXT=https://github.com/crunchdao/coordinator-webapp.git
REPORT_UI_DOCKERFILE=apps/starter/Dockerfile

FEED_SOURCE=pyth
FEED_SUBJECTS=BTC
FEED_KIND=tick
FEED_GRANULARITY=1s
FEED_POLL_SECONDS=5
FEED_BACKFILL_MINUTES=180
FEED_CANDLES_WINDOW=120
FEED_RECORD_TTL_DAYS=90
FEED_RETENTION_CHECK_SECONDS=3600

CRUNCH_ID={config.crunch_id}
MODEL_BASE_CLASSNAME={config.model_base_classname}
CHECKPOINT_INTERVAL_SECONDS={config.checkpoint_interval_seconds}

{callables_block}
"""
