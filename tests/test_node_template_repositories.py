import inspect
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

    def test_prediction_repository_has_query_scores_method(self):
        self.assertTrue(callable(getattr(DBPredictionRepository, "query_scores", None)))

    def test_leaderboard_repository_has_required_methods(self):
        self.assertTrue(callable(getattr(DBLeaderboardRepository, "save", None)))
        self.assertTrue(callable(getattr(DBLeaderboardRepository, "get_latest", None)))

    def test_input_repository_save_updates_scope_and_resolvable_at(self):
        """Regression: DBInputRepository.save() must update scope_jsonb and
        resolvable_at on existing records, not just status/actuals/meta."""
        source = inspect.getsource(DBInputRepository.save)
        self.assertIn("scope_jsonb", source,
                       "save() must update scope_jsonb on existing records")
        self.assertIn("resolvable_at", source,
                       "save() must update resolvable_at on existing records")


if __name__ == "__main__":
    unittest.main()
