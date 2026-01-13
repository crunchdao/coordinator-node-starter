from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional

from condorgame_backend.entities.prediction import Prediction, PredictionConfig, PredictionParams


@dataclass
class WindowedScoreRow:
    model_id: str
    asset: str
    horizon: int
    steps: tuple[int,...]
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

    # todo type the result
    @abstractmethod
    def query_scores(self, model_ids: list[str], _from: Optional[datetime], to: Optional[datetime]) -> dict[str, list[dict]]:
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
                       "steps": tuple[int,...],
                       "count": int,
                       "mean": float,
                   }
        """
        pass

    @abstractmethod
    # Will remove all the predictions scored and who has more than 10 days
    def prune(self):
        pass

    @abstractmethod
    def get_latest_prediction_params_execution_time(self) -> list[(PredictionParams, datetime)]:
        pass
