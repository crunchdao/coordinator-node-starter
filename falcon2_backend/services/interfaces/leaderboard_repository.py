from abc import ABC, abstractmethod
from typing import Optional

from falcon2_backend.entities.leaderboard import Leaderboard


class LeaderboardRepository(ABC):

    @abstractmethod
    def save(self, leaderboard: Leaderboard):
        pass

    @abstractmethod
    def get_latest(self) -> Optional[Leaderboard]:
        pass