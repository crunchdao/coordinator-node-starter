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
    markers = [
        "BAD_IMPLEMENTATION",
        "No Inherited class found",
        "Import error occurred",
    ]
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
        "-f",
        "docker-compose-local.yml",
        "--env-file",
        ".local.env",
        "logs",
        "model-orchestrator",
        "--tail",
        "300",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return (result.stdout or "") + "\n" + (result.stderr or "")


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
            if os.getenv("E2E_SKIP_MODEL_RUNNER_LOG_CHECK", "0") != "1":
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

            scored = [row for row in predictions if row.get("score_value") is not None and row.get("score_failed") is False]
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
