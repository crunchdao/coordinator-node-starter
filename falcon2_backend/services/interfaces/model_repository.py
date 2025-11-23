from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable, Optional

from falcon2_backend.entities.model import Model, ModelScoreSnapshot


class ModelRepository(ABC):

    @abstractmethod
    def fetch_all(self) -> dict[str, Model]:
        pass

    @abstractmethod
    def fetch_by_ids(self, ids: list[str]) -> dict[str, Model]:
        pass

    @abstractmethod
    def fetch(self, model_id) -> Model:
        pass

    @abstractmethod
    def save(self, model: Model):
        pass

    @abstractmethod
    def save_all(self, models: Iterable[Model]):
        pass

    @abstractmethod
    def snapshot_model_scores(self, model_score_snapshots: Iterable[ModelScoreSnapshot]):
        pass

    @abstractmethod
    def fetch_model_score_snapshots(self, model_ids: list[str], _from: Optional[datetime], to: Optional[datetime]) -> dict[str, list[ModelScoreSnapshot]]:
        pass

    @abstractmethod
    def prune_snapshots(self):
        pass
