from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from coordinator.entities.prediction import PredictionRecord


class PredictionRepository(ABC):

    @abstractmethod
    def save(self, prediction: PredictionRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_all(self, predictions: Iterable[PredictionRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def find(
        self,
        *,
        status: str | list[str] | None = None,
        scope_key: str | None = None,
        model_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        resolvable_before: datetime | None = None,
        limit: int | None = None,
    ) -> list[PredictionRecord]:
        raise NotImplementedError

    def fetch_active_configs(self) -> list[dict]:
        return []
