from __future__ import annotations

import shutil
from pathlib import Path

from coordinator_cli.commands.init_config import resolve_init_config
from coordinator_cli.commands.init_scaffold import (
    render_scaffold_files,
    vendor_runtime_packages,
    write_process_log,
    write_tree,
)


def run_init(
    name: str,
    project_root: Path,
    force: bool = False,
) -> int:
    try:
        config = resolve_init_config(name)
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
        files = render_scaffold_files(config)
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
            },
            {
                "phase": "init",
                "action": "runtime_vendored",
                "status": "ok",
                "runtime_dir": str(workspace_dir / config.node_name / "runtime"),
            },
        ],
    )

    print()
    print(f"✅ Coordinator folder initiated: {workspace_dir}")
    print()
    print(f"  cd {workspace_dir}")
    print()
    print("Start your agent within the folder and say:")
    print('  "create the crunch with me"')
    print("It will step you through the process.")
    return 0
