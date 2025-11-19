from abc import ABC, abstractmethod
from typing import Iterable

from falcon2_backend.entities.model import Model


class ModelRepository(ABC):

    @abstractmethod
    def fetch_all(self) -> dict[str, Model]:
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
