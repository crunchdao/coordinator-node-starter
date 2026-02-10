from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from coordinator_core.entities.model import Model


class ModelRepository(ABC):
    @abstractmethod
    def fetch_all(self) -> dict[str, Model]:
        raise NotImplementedError

    @abstractmethod
    def fetch_by_ids(self, ids: list[str]) -> dict[str, Model]:
        raise NotImplementedError

    @abstractmethod
    def fetch(self, model_id: str) -> Model | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, model: Model) -> None:
        raise NotImplementedError

    @abstractmethod
    def save_all(self, models: Iterable[Model]) -> None:
        raise NotImplementedError
