from falcon2_backend.entities.prediction import Prediction, PredictionConfig, PredictionParams
from typing import List

from falcon2_backend.services.interfaces.prediction_repository import PredictionRepository

HOUR = 60 * 60
MINUTE = 60
DAY = 24 * HOUR


class InMemoryPredictionRepository(PredictionRepository):
    def __init__(self):
        # In-memory storage
        self._storage: List[Prediction] = []
        self._config_storage: List[PredictionConfig] = [
            PredictionConfig(PredictionParams('BTC', 1 * DAY, 5 * MINUTE), 1 * HOUR, True, 1),
            PredictionConfig(PredictionParams('BTC', 1 * HOUR, 1 * MINUTE), 12 * MINUTE, True, 2),

            PredictionConfig(PredictionParams('ETH', 1 * DAY, 5 * MINUTE), 1 * HOUR, True, 1),
            PredictionConfig(PredictionParams('ETH', 1 * HOUR, 1 * MINUTE), 12 * MINUTE, True, 2),

            PredictionConfig(PredictionParams('XAU', 1 * DAY, 5 * MINUTE), 1 * HOUR, True, 1),
            PredictionConfig(PredictionParams('XAU', 1 * HOUR, 1 * MINUTE), 12 * MINUTE, True, 2),

            PredictionConfig(PredictionParams('SOL', 1 * DAY, 5 * MINUTE), 1 * HOUR, True, 1),
            PredictionConfig(PredictionParams('SOL', 1 * HOUR, 1 * MINUTE), 12 * MINUTE, True, 2),
        ]

    def save(self, prediction: Prediction):
        """Save a single prediction."""
        self._storage.append(prediction)

    def save_all(self, predictions: List[Prediction]):
        """Save a list of predictions."""
        self._storage.extend(predictions)

    def fetch_all(self) -> List[Prediction]:
        """Fetch all saved predictions."""
        return self._storage

    def clear(self):
        """Clear all stored predictions (only for testing)."""
        self._storage.clear()

    def fetch_active_configs(self) -> List[PredictionConfig]:
        """Fetch all active AssetConfig items."""
        return [config for config in self._config_storage if config.active]
