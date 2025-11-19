from abc import ABC, abstractmethod

from falcon2_backend.entities.leaderboard import Leaderboard


class LeaderboardRepository(ABC):

    @abstractmethod
    def save(self, leaderboard: Leaderboard):
        pass
