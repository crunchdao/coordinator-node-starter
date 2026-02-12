from __future__ import annotations

import shutil
from pathlib import Path

from coordinator_core.cli.init_config import (
    load_answers,
    load_spec,
    merge_answers_with_spec,
    resolve_init_config,
)
from coordinator_core.cli.init_scaffold import (
    render_scaffold_files,
    vendor_runtime_packages,
    write_process_log,
    write_tree,
)
from coordinator_core.cli.packs import list_pack_summaries


def run_init(
    name: str | None,
    project_root: Path,
    force: bool = False,
    spec_path: Path | None = None,
    answers_path: Path | None = None,
    pack_name: str | None = None,
    list_packs: bool = False,
) -> int:
    if list_packs:
        print("Available packs:")
        for pack, description in list_pack_summaries():
            print(f"- {pack}: {description}")
        return 0

    try:
        answers = load_answers(answers_path) if answers_path is not None else {}
        spec = load_spec(spec_path) if spec_path is not None else {}
        merged_spec = merge_answers_with_spec(answers=answers, spec=spec)
        config = resolve_init_config(
            name=name,
            spec=merged_spec,
            require_spec_version=spec_path is not None,
            pack_name=pack_name,
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
        files = render_scaffold_files(config=config, include_spec=spec_path is not None)
    except ValueError as exc:
        print(str(exc))
        return 1

    write_tree(workspace_dir, files)
    try:
        vendor_runtime_packages(workspace_dir / config.node_name / "runtime")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to vendor runtime packages: {exc}")
        return 1

    write_process_log(
        workspace_dir,
        [
            {
                "phase": "init",
                "action": "scaffold_created",
                "status": "ok",
                "workspace": str(workspace_dir),
                "challenge": config.name,
                "pack": config.pack,
            },
            {
                "phase": "init",
                "action": "runtime_vendored",
                "status": "ok",
                "runtime_dir": str(workspace_dir / config.node_name / "runtime"),
            },
        ],
    )

    print(f"Scaffold created: {workspace_dir}")
    print(f"Next: cd {workspace_dir / config.node_name}")
    return 0
