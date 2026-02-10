from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LeaderboardRepository(ABC):
    @abstractmethod
    def save(self, leaderboard_entries: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_latest(self) -> dict[str, Any] | None:
        raise NotImplementedError
