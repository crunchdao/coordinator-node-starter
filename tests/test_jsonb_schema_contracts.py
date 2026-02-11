import unittest

from pydantic import ValidationError

from coordinator_core.schemas.payload_contracts import (
    LeaderboardEntryEnvelope,
    PredictionScopeEnvelope,
    ScheduleEnvelope,
    ScheduledPredictionConfigEnvelope,
    ScoreEnvelope,
)


class TestJsonbSchemaContracts(unittest.TestCase):
    def test_schedule_envelope_validates_intervals(self):
        schedule = ScheduleEnvelope(prediction_interval_seconds=60, resolve_after_seconds=120)
        self.assertEqual(schedule.prediction_interval_seconds, 60)
        self.assertEqual(schedule.resolve_after_seconds, 120)

        with self.assertRaises(ValidationError):
            ScheduleEnvelope(prediction_interval_seconds=0, resolve_after_seconds=120)

    def test_scheduled_prediction_config_envelope_roundtrip(self):
        cfg = ScheduledPredictionConfigEnvelope(
            id="CFG_001",
            scope_key="BTC-60-60",
            scope_template={"asset": "BTC", "horizon": 60, "step": 60},
            schedule={"prediction_interval_seconds": 60, "resolve_after_seconds": 60},
            active=True,
            order=1,
            meta={"profile": "starter"},
        )

        dumped = cfg.model_dump()
        self.assertEqual(dumped["scope_key"], "BTC-60-60")
        self.assertEqual(dumped["schedule"]["prediction_interval_seconds"], 60)

    def test_prediction_scope_envelope_requires_scope_key(self):
        scope = PredictionScopeEnvelope(scope_key="BTC-60-60", scope={"asset": "BTC"})
        self.assertEqual(scope.scope["asset"], "BTC")

        with self.assertRaises(ValidationError):
            PredictionScopeEnvelope(scope_key="", scope={})

    def test_score_and_leaderboard_envelopes(self):
        score = ScoreEnvelope(
            windows={"recent": 0.2, "steady": 0.3, "anchor": 0.4},
            rank_key=0.4,
            payload={"metric": "brier"},
        )

        entry = LeaderboardEntryEnvelope(
            model_id="m1",
            score=score,
            rank=1,
            model_name="model-one",
            cruncher_name="alice",
        )

        self.assertEqual(entry.score.windows["anchor"], 0.4)
        self.assertEqual(entry.rank, 1)


if __name__ == "__main__":
    unittest.main()
