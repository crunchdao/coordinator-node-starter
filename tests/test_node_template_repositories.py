import unittest

from coordinator_node.db.repositories import (
    DBInputRepository,
    DBLeaderboardRepository,
    DBModelRepository,
    DBPredictionRepository,
    DBScoreRepository,
)


class TestRepositoryAPIs(unittest.TestCase):
    def test_model_repository_has_required_methods(self):
        self.assertTrue(callable(getattr(DBModelRepository, "fetch_all", None)))
        self.assertTrue(callable(getattr(DBModelRepository, "save", None)))

    def test_input_repository_has_required_methods(self):
        self.assertTrue(callable(getattr(DBInputRepository, "save", None)))
        self.assertTrue(callable(getattr(DBInputRepository, "find", None)))

    def test_prediction_repository_has_required_methods(self):
        self.assertTrue(callable(getattr(DBPredictionRepository, "save", None)))
        self.assertTrue(callable(getattr(DBPredictionRepository, "save_all", None)))
        self.assertTrue(callable(getattr(DBPredictionRepository, "find", None)))

    def test_score_repository_has_required_methods(self):
        self.assertTrue(callable(getattr(DBScoreRepository, "save", None)))
        self.assertTrue(callable(getattr(DBScoreRepository, "find", None)))

    def test_leaderboard_repository_has_required_methods(self):
        self.assertTrue(callable(getattr(DBLeaderboardRepository, "save", None)))
        self.assertTrue(callable(getattr(DBLeaderboardRepository, "get_latest", None)))


if __name__ == "__main__":
    unittest.main()
