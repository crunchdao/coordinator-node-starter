from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord, PredictionScore
from node_template.extensions.risk_adjusted_callables import (
    aggregate_model_scores_sharpe_like,
    rank_leaderboard_risk_adjusted,
)


class TestRiskAdjustedCallables(unittest.TestCase):
    def _prediction(self, model_id: str, value: float) -> PredictionRecord:
        now = datetime.now(timezone.utc)
        prediction = PredictionRecord(
            id=f"p-{model_id}-{value}",
            model_id=model_id,
            prediction_config_id="CFG_001",
            scope_key="BTC-60",
            scope={"asset": "BTC", "horizon": 60, "step": 60},
            status="SUCCESS",
            exec_time_ms=1.0,
            inference_input={},
            inference_output={},
            performed_at=now - timedelta(minutes=2),
            resolvable_at=now - timedelta(minutes=1),
        )
        prediction.score = PredictionScore(value=value, success=True, failed_reason=None)
        return prediction

    def test_aggregate_model_scores_sharpe_like_emits_metrics_and_ranking(self):
        scored_predictions = [
            self._prediction("m1", 0.02),
            self._prediction("m1", -0.01),
            self._prediction("m2", 0.03),
            self._prediction("m2", -0.03),
        ]
        models = {
            "m1": Model(
                id="m1",
                name="model-one",
                player_id="p1",
                player_name="alice",
                deployment_identifier="d1",
            ),
            "m2": Model(
                id="m2",
                name="model-two",
                player_id="p2",
                player_name="bob",
                deployment_identifier="d2",
            ),
        }

        entries = aggregate_model_scores_sharpe_like(scored_predictions, models)
        self.assertEqual(len(entries), 2)

        m1 = next(entry for entry in entries if entry["model_id"] == "m1")
        self.assertIn("score", m1)
        self.assertIn("metrics", m1["score"])
        self.assertIn("ranking", m1["score"])
        self.assertEqual(m1["score"]["ranking"]["key"], "sharpe_like")
        self.assertIn("wealth", m1["score"]["metrics"])
        self.assertIn("sharpe_like", m1["score"]["metrics"])

    def test_rank_leaderboard_risk_adjusted_uses_tie_breakers(self):
        entries = [
            {
                "model_id": "m1",
                "score": {
                    "metrics": {"sharpe_like": 1.2, "wealth": 1.10},
                    "ranking": {"key": "sharpe_like", "direction": "desc", "tie_breakers": ["wealth"]},
                    "payload": {},
                },
            },
            {
                "model_id": "m2",
                "score": {
                    "metrics": {"sharpe_like": 1.2, "wealth": 1.25},
                    "ranking": {"key": "sharpe_like", "direction": "desc", "tie_breakers": ["wealth"]},
                    "payload": {},
                },
            },
        ]

        ranked = rank_leaderboard_risk_adjusted(entries)
        self.assertEqual([entry["model_id"] for entry in ranked], ["m2", "m1"])
        self.assertEqual([entry["rank"] for entry in ranked], [1, 2])


if __name__ == "__main__":
    unittest.main()
