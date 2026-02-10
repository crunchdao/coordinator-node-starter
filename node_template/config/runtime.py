from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class RuntimeSettings:
    checkpoint_interval_seconds: int
    model_runner_node_host: str
    model_runner_node_port: int
    model_runner_timeout_seconds: int
    crunch_id: str
    base_classname: str

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        return cls(
            checkpoint_interval_seconds=int(os.getenv("CHECKPOINT_INTERVAL_SECONDS", "900")),
            model_runner_node_host=os.getenv("MODEL_RUNNER_NODE_HOST", "model-orchestrator"),
            model_runner_node_port=int(os.getenv("MODEL_RUNNER_NODE_PORT", "9091")),
            model_runner_timeout_seconds=int(os.getenv("MODEL_RUNNER_TIMEOUT_SECONDS", "60")),
            crunch_id=os.getenv("CRUNCH_ID", "condorgame"),
            base_classname=os.getenv("MODEL_BASE_CLASSNAME", "condorgame.tracker.TrackerBase"),
        )
