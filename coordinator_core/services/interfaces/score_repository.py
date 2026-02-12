from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from coordinator_core.entities.prediction import ScoreRecord


class ScoreRepository(ABC):
    @abstractmethod
    def save(self, record: ScoreRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def find(
        self,
        *,
        prediction_id: str | None = None,
        model_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[ScoreRecord]:
        raise NotImplementedError
