from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
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

    def fetch_active_configs(self) -> list[dict]:
        return []

    def fetch_scored_predictions(self) -> list[PredictionRecord]:
        return []

    def query_scores(
        self,
        model_ids: list[str],
        _from: datetime | None,
        to: datetime | None,
    ) -> dict[str, list[PredictionRecord]]:
        return {}
