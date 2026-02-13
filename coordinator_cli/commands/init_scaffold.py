from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coordinator_cli.commands.init_config import InitConfig

_BASE_DIR = Path(__file__).resolve().parent.parent.parent / "base"
_PACKS_DIR = Path(__file__).resolve().parent.parent.parent / "packs"

# Tokens to replace in file contents and directory names
_REPLACEMENTS = {
    "starter-challenge": "{name}",
    "starter_challenge": "{module}",
}


def render_workspace(config: InitConfig, pack: str | None = None) -> Path:
    """Copy base/ to destination, optionally overlay a pack, replace tokens."""
    dest = config.dest

    if not _BASE_DIR.exists():
        raise ValueError(f"Base template not found at {_BASE_DIR}")

    # 1. Copy base
    shutil.copytree(_BASE_DIR, dest, dirs_exist_ok=True)

    # 2. Overlay pack (if any)
    if pack:
        pack_dir = _PACKS_DIR / pack
        if not pack_dir.exists():
            raise ValueError(f"Pack '{pack}' not found at {pack_dir}")
        shutil.copytree(pack_dir, dest, dirs_exist_ok=True)

    # 3. Replace tokens in file contents
    replacements = {
        "starter-challenge": config.name,
        "starter_challenge": config.module,
    }
    _replace_in_tree(dest, replacements)

    # 4. Rename Python package directory
    old_pkg = dest / "challenge" / "starter_challenge"
    new_pkg = dest / "challenge" / config.module
    if old_pkg.exists() and old_pkg != new_pkg:
        old_pkg.rename(new_pkg)

    # 5. Vendor coordinator runtime
    vendor_runtime(dest / "node" / "runtime")

    # 6. Write process log
    _write_process_log(dest, config)

    return dest


def vendor_runtime(target_dir: Path) -> None:
    """Copy the coordinator package into the node runtime directory."""
    import coordinator

    source = Path(coordinator.__file__).resolve().parent
    destination = target_dir / "coordinator"
    target_dir.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _replace_in_tree(root: Path, replacements: dict[str, str]) -> None:
    """Replace tokens in all text files under root."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        # Skip binary files
        if path.suffix in (".pyc", ".pyo", ".so", ".dylib", ".whl", ".tar", ".gz", ".zip", ".png", ".jpg", ".pdf"):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        new_content = content
        for old, new in replacements.items():
            new_content = new_content.replace(old, new)
        if new_content != content:
            path.write_text(new_content, encoding="utf-8")


def _write_process_log(dest: Path, config: InitConfig) -> None:
    path = dest / "process-log.jsonl"
    events = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "init",
            "action": "workspace_created",
            "status": "ok",
            "name": config.name,
            "workspace": str(dest),
        },
    ]
    lines = [json.dumps(e, separators=(",", ":")) for e in events]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
