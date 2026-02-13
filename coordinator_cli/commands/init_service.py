from __future__ import annotations

import shutil
from pathlib import Path

from coordinator_cli.commands.init_config import resolve_init_config
from coordinator_cli.commands.init_scaffold import render_workspace


def run_init(name: str, project_root: Path, force: bool = False) -> int:
    try:
        config = resolve_init_config(name, project_root)
    except ValueError as exc:
        print(str(exc))
        return 1

    if config.dest.exists():
        if not force:
            print(f"Target already exists: {config.dest}. Use --force to overwrite.")
            return 1
        shutil.rmtree(config.dest)

    try:
        render_workspace(config)
    except (ValueError, OSError) as exc:
        print(f"Failed: {exc}")
        return 1

    print()
    print(f"✅ Created {config.dest}")
    print()
    print(f"  cd {config.dest}")
    print(f"  make deploy")
    print()
    print("Or start your agent within the folder and say:")
    print('  "create the crunch with me"')
    return 0
