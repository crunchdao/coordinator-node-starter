from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from coordinator_core.entities.prediction import PredictionRecord


class PredictionRepository(ABC):
    @abstractmethod
    def save(self, prediction: PredictionRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_all(self, predictions: Iterable[PredictionRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def fetch_ready_to_score(self) -> list[PredictionRecord]:
        raise NotImplementedError
