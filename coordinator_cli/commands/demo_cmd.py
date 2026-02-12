from __future__ import annotations

import subprocess
from pathlib import Path

from coordinator_cli.commands.init_service import run_init


def run_demo(
    *,
    output_root: Path,
    force: bool = False,
    webapp_path: Path | None = None,
    start: bool = False,
) -> int:
    challenge_name = "btc-up"

    code = run_init(
        name=challenge_name,
        project_root=output_root,
        force=force,
        pack_name="baseline",
    )
    if code != 0:
        return code

    node_dir = output_root / challenge_name / f"crunch-node-{challenge_name}"
    env_path = node_dir / ".local.env"

    if webapp_path is not None:
        resolved_webapp = webapp_path.expanduser().resolve()
        if not resolved_webapp.exists():
            print(f"demo failed: local webapp path not found: {resolved_webapp}")
            return 1
        _upsert_env_value(env_path, "REPORT_UI_BUILD_CONTEXT", str(resolved_webapp))

    if start:
        command = [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "--env-file",
            ".local.env",
            "up",
            "-d",
            "--build",
        ]
        try:
            subprocess.run(command, cwd=node_dir, check=True)
        except subprocess.CalledProcessError as exc:
            print(f"demo failed: could not start stack ({exc.returncode})")
            return 1

    print(f"Demo workspace ready: {node_dir}")
    if not start:
        print("Next: cd {} && make deploy".format(node_dir))
    return 0


def _upsert_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    new_line = f"{key}={value}"

    replaced = False
    updated: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            updated.append(new_line)
            replaced = True
        else:
            updated.append(line)

    if not replaced:
        updated.append(new_line)

    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")
