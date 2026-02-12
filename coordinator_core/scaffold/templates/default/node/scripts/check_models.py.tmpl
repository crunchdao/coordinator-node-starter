"""Pre-deploy model health check.

Waits for all models in the orchestrator to reach RUNNING state.
Fails fast if model build/setup errors are detected in logs.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time


_FAILURE_MARKERS = [
    "BAD_IMPLEMENTATION",
    "No Inherited class found",
    "Import error occurred",
    "BuilderStatus.FAILURE",
    "ModuleNotFoundError",
    "SyntaxError",
]

_SUCCESS_MARKERS = [
    "is RUNNING on",
    "RunnerStatus.RUNNING",
]


def _read_orchestrator_logs() -> str:
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
        "500",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return (result.stdout or "") + "\n" + (result.stderr or "")


def _detect_failure(log_text: str) -> str | None:
    for line in log_text.splitlines():
        for marker in _FAILURE_MARKERS:
            if marker in line:
                return line.strip()
    return None


def _detect_running(log_text: str) -> bool:
    for line in log_text.splitlines():
        for marker in _SUCCESS_MARKERS:
            if marker in line:
                return True
    return False


def main() -> int:
    timeout_seconds = int(os.getenv("CHECK_MODELS_TIMEOUT_SECONDS", "120"))
    poll_seconds = int(os.getenv("CHECK_MODELS_POLL_SECONDS", "3"))

    print(f"[check-models] waiting up to {timeout_seconds}s for models to reach RUNNING")

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        logs = _read_orchestrator_logs()

        failure = _detect_failure(logs)
        if failure is not None:
            print(f"[check-models] FAILED: model error detected")
            print(f"  {failure}")
            print()
            print("[check-models] Recent orchestrator logs:")
            for line in logs.splitlines()[-30:]:
                print(f"  {line}")
            return 1

        if _detect_running(logs):
            print("[check-models] OK: all models reached RUNNING state")
            return 0

        time.sleep(poll_seconds)

    print(f"[check-models] FAILED: timeout after {timeout_seconds}s — no model reached RUNNING")
    print()
    print("[check-models] Recent orchestrator logs:")
    logs = _read_orchestrator_logs()
    for line in logs.splitlines()[-30:]:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
