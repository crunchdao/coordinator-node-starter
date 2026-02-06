from abc import ABC, abstractmethod
from typing import Optional

from condorgame_backend.entities.daily_synth_leaderboard import DailySynthLeaderboard


class SynthLeaderboardRepository(ABC):

    @abstractmethod
    def save(self, leaderboard: DailySynthLeaderboard):
        pass

    @abstractmethod
    def get_latest(self) -> Optional[DailySynthLeaderboard]:
        pass