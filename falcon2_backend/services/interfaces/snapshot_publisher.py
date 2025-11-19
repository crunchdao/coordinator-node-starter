from abc import ABC, abstractmethod
from typing import Iterable

from falcon2_backend.entities.leaderboard import Leaderboard
from falcon2_backend.entities.model import Model


class SnapshotPublisher(ABC):

    @abstractmethod
    def publish_leaderboard(self, leaderboard: Leaderboard):
        pass

    @abstractmethod
    def publish_models(self, models: Iterable[Model]):
        pass