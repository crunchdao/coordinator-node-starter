from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class RuntimeSettings:
    checkpoint_interval_seconds: int
    model_runner_node_host: str
    model_runner_node_port: int
    model_runner_timeout_seconds: float
    crunch_id: str
    crunch_pubkey: str
    network: str
    base_classname: str
    feed_provider: str
    feed_record_ttl_days: int

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        return cls(
            checkpoint_interval_seconds=int(os.getenv("CHECKPOINT_INTERVAL_SECONDS", "900")),
            model_runner_node_host=os.getenv("MODEL_RUNNER_NODE_HOST", "model-orchestrator"),
            model_runner_node_port=int(os.getenv("MODEL_RUNNER_NODE_PORT", "9091")),
            model_runner_timeout_seconds=float(os.getenv("MODEL_RUNNER_TIMEOUT_SECONDS", "60")),
            crunch_id=os.getenv("CRUNCH_ID", "starter-challenge"),
            crunch_pubkey=os.getenv("CRUNCH_PUBKEY", ""),
            network=os.getenv("NETWORK", "devnet"),
            base_classname=os.getenv("MODEL_BASE_CLASSNAME", "tracker.TrackerBase"),
            feed_provider=os.getenv("FEED_PROVIDER", "pyth"),
            feed_record_ttl_days=int(os.getenv("FEED_RECORD_TTL_DAYS", "90")),
        )
