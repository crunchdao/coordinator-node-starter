from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ModelScore:
    metrics: dict[str, float | None] = field(default_factory=dict)
    ranking: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Model:
    id: str
    name: str
    player_id: str
    player_name: str
    deployment_identifier: str
    overall_score: ModelScore | None = None
    scores_by_scope: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)           # contract.meta_type (Meta)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
