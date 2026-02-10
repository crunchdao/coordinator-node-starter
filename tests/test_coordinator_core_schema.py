import unittest

from coordinator_core.infrastructure.db.db_tables import (
    CheckpointRow,
    EmissionCheckpointRow,
    LeaderboardRow,
    ModelRow,
    ModelScoreRow,
    PredictionConfigRow,
    PredictionRow,
)


class TestCoordinatorCoreSchema(unittest.TestCase):
    def test_required_table_names(self):
        self.assertEqual(ModelRow.__tablename__, "models")
        self.assertEqual(PredictionRow.__tablename__, "predictions")
        self.assertEqual(ModelScoreRow.__tablename__, "model_scores")
        self.assertEqual(LeaderboardRow.__tablename__, "leaderboards")
        self.assertEqual(CheckpointRow.__tablename__, "checkpoints")
        self.assertEqual(EmissionCheckpointRow.__tablename__, "emission_checkpoints")
        self.assertEqual(PredictionConfigRow.__tablename__, "prediction_configs")

    def test_jsonb_extension_fields_exist(self):
        self.assertIn("overall_score_jsonb", ModelRow.model_fields)
        self.assertIn("scores_by_scope_jsonb", ModelRow.model_fields)
        self.assertIn("meta_jsonb", ModelRow.model_fields)

        self.assertIn("inference_input_jsonb", PredictionRow.model_fields)
        self.assertIn("inference_output_jsonb", PredictionRow.model_fields)
        self.assertIn("scope_jsonb", PredictionRow.model_fields)
        self.assertIn("meta_jsonb", PredictionRow.model_fields)

        self.assertIn("score_payload_jsonb", ModelScoreRow.model_fields)
        self.assertIn("entries_jsonb", LeaderboardRow.model_fields)
        self.assertIn("meta_jsonb", LeaderboardRow.model_fields)

        self.assertIn("meta_jsonb", CheckpointRow.model_fields)
        self.assertIn("payload_jsonb", EmissionCheckpointRow.model_fields)

        self.assertIn("scope_template_jsonb", PredictionConfigRow.model_fields)
        self.assertIn("schedule_jsonb", PredictionConfigRow.model_fields)
        self.assertIn("meta_jsonb", PredictionConfigRow.model_fields)

    def test_prediction_protocol_columns_exist(self):
        required_prediction_fields = {
            "id",
            "model_id",
            "prediction_config_id",
            "scope_key",
            "scope_jsonb",
            "status",
            "performed_at",
            "resolvable_at",
            "score_value",
            "score_success",
            "score_failed_reason",
            "score_scored_at",
        }

        self.assertTrue(required_prediction_fields.issubset(PredictionRow.model_fields.keys()))


if __name__ == "__main__":
    unittest.main()
