from __future__ import annotations

import unittest
from datetime import datetime, timezone

from coordinator_core.entities.model import Model
from coordinator_core.services.interfaces.leaderboard_repository import LeaderboardRepository
from coordinator_core.services.interfaces.model_repository import ModelRepository
from node_template.workers.report_worker import get_leaderboard, get_models


class InMemoryModelRepository(ModelRepository):
    def __init__(self, models: dict[str, Model]):
        self._models = models

    def fetch_all(self) -> dict[str, Model]:
        return self._models

    def fetch_by_ids(self, ids: list[str]) -> dict[str, Model]:
        return {k: v for k, v in self._models.items() if k in ids}

    def fetch(self, model_id: str) -> Model | None:
        return self._models.get(model_id)

    def save(self, model: Model) -> None:
        self._models[model.id] = model

    def save_all(self, models):
        for model in models:
            self.save(model)


class InMemoryLeaderboardRepository(LeaderboardRepository):
    def __init__(self, latest: dict | None):
        self._latest = latest

    def save(self, leaderboard_entries, meta=None) -> None:
        self._latest = {
            "id": "lbr",
            "created_at": datetime.now(timezone.utc),
            "entries": leaderboard_entries,
            "meta": meta or {},
        }

    def get_latest(self) -> dict | None:
        return self._latest


class TestNodeTemplateReportWorker(unittest.TestCase):
    def test_get_models_returns_expected_shape(self):
        models = {
            "m1": Model(
                id="m1",
                name="model-alpha",
                player_id="p1",
                player_name="alice",
                deployment_identifier="d1",
            )
        }
        repo = InMemoryModelRepository(models)

        response = get_models(repo)
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]["model_id"], "m1")
        self.assertEqual(response[0]["model_name"], "model-alpha")
        self.assertEqual(response[0]["cruncher_name"], "alice")

    def test_get_leaderboard_sorts_by_rank(self):
        latest = {
            "id": "l1",
            "created_at": datetime(2026, 2, 10, tzinfo=timezone.utc),
            "entries": [
                {
                    "rank": 2,
                    "model_id": "m2",
                    "score_recent": 0.2,
                    "score_steady": 0.2,
                    "score_anchor": 0.2,
                    "model_name": "two",
                    "cruncher_name": "bob",
                },
                {
                    "rank": 1,
                    "model_id": "m1",
                    "score_recent": 0.3,
                    "score_steady": 0.3,
                    "score_anchor": 0.3,
                    "model_name": "one",
                    "cruncher_name": "alice",
                },
            ],
            "meta": {},
        }
        repo = InMemoryLeaderboardRepository(latest)

        response = get_leaderboard(repo)
        self.assertEqual([entry["rank"] for entry in response], [1, 2])
        self.assertEqual(response[0]["model_id"], "m1")

    def test_get_leaderboard_returns_empty_when_missing(self):
        repo = InMemoryLeaderboardRepository(None)
        self.assertEqual(get_leaderboard(repo), [])


if __name__ == "__main__":
    unittest.main()
