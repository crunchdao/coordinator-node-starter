from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ModelScore:
    recent: float | None = None
    steady: float | None = None
    anchor: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Model:
    id: str
    name: str
    player_id: str
    player_name: str
    deployment_identifier: str
    overall_score: ModelScore | None = None
    scores_by_param: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
