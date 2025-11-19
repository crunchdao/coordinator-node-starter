from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Iterable

from falcon2_backend.entities.prediction import Prediction, PredictionConfig


@dataclass
class WindowedScoreRow:
    model_id: str
    asset: str
    horizon: int
    step: int
    count: int
    recent_mean: float
    steady_mean: float
    anchor_mean: float

class PredictionRepository(ABC):

    @abstractmethod
    def save(self, prediction: Prediction):
        pass

    @abstractmethod
    def save_all(self, predictions: Iterable[Prediction]):
        pass

    @abstractmethod
    def fetch_ready_to_score(self) -> list[Prediction]:
        pass

    @abstractmethod
    def fetch_active_configs(self) -> list[PredictionConfig]:
        pass

    @abstractmethod
    def fetch_all_windowed_scores(self) -> list[WindowedScoreRow]:
        """
               Returns, for each window, the list of rows:
                   {
                       "model_id": str,
                       "asset": str,
                       "horizon": int,
                       "step": int,
                       "count": int,
                       "mean": float,
                   }
        """
        pass

    @abstractmethod
    # Will remove all the predictions scored and who has more than 10 days
    def clean(self):
        pass
