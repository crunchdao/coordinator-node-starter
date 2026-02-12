from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Checkpoint:
    id: str
    checkpoint_kind: str
    interval_seconds: int
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmissionCheckpoint:
    id: str
    checkpoint_id: str
    emitted_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
