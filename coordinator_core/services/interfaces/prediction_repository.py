from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Iterable

from coordinator_core.entities.prediction import PredictionRecord


class PredictionRepository(ABC):

    # ── write ──

    @abstractmethod
    def save_prediction(self, prediction: PredictionRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_predictions(self, predictions: Iterable[PredictionRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_actuals(self, prediction_id: str, actuals: dict[str, Any]) -> None:
        raise NotImplementedError

    # ── query ──

    @abstractmethod
    def find_predictions(
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

    # ── config ──

    def fetch_active_configs(self) -> list[dict]:
        return []

    # ── legacy compat ──

    def save(self, prediction: PredictionRecord) -> None:
        self.save_prediction(prediction)

    def save_all(self, predictions: Iterable[PredictionRecord]) -> None:
        self.save_predictions(predictions)

    def fetch_ready_to_score(self) -> list[PredictionRecord]:
        return self.find_predictions(status="RESOLVED")

    def fetch_scored_predictions(self) -> list[PredictionRecord]:
        return self.find_predictions(status="SCORED")

    def query_scores(
        self,
        model_ids: list[str],
        _from: datetime | None,
        to: datetime | None,
    ) -> dict[str, list[PredictionRecord]]:
        result: dict[str, list[PredictionRecord]] = {}
        for model_id in model_ids:
            result[model_id] = self.find_predictions(
                status="SCORED", model_id=model_id, since=_from, until=to,
            )
        return result
