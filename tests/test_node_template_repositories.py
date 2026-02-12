import inspect
import unittest

from coordinator.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator.interfaces.model_repository import ModelRepository
from coordinator.interfaces.prediction_repository import PredictionRepository
from coordinator.db.repositories import (
    DBLeaderboardRepository,
    DBModelRepository,
    DBPredictionRepository,
)


class TestNodeTemplateRepositories(unittest.TestCase):
    def test_repository_types_follow_core_interfaces(self):
        self.assertTrue(issubclass(DBModelRepository, ModelRepository))
        self.assertTrue(issubclass(DBPredictionRepository, PredictionRepository))
        self.assertTrue(issubclass(DBLeaderboardRepository, LeaderboardRepository))

    def test_model_repository_exposes_required_methods(self):
        methods = {name for name, _ in inspect.getmembers(DBModelRepository, inspect.isfunction)}
        self.assertIn("fetch_all", methods)
        self.assertIn("save", methods)


if __name__ == "__main__":
    unittest.main()
