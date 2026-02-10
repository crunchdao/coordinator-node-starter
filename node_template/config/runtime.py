from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class RuntimeSettings:
    checkpoint_interval_seconds: int

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        return cls(
            checkpoint_interval_seconds=int(os.getenv("CHECKPOINT_INTERVAL_SECONDS", "900")),
        )
