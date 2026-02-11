from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TrackerBase:
    """Minimal tracker contract used by the local starter submission."""

    history: dict[str, list[tuple[int, float]]] = field(default_factory=lambda: defaultdict(list))

    def tick(self, data: dict[str, list[tuple[int, float]]]) -> None:
        for asset, points in (data or {}).items():
            self.history.setdefault(asset, []).extend(points or [])

    def predict(self, asset: str, horizon: int, step: int):  # pragma: no cover - interface method
        raise NotImplementedError
