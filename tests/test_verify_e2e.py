import unittest

from scripts.verify_e2e import _detect_model_runner_failure, _detect_prediction_validation_failure


class TestVerifyE2E(unittest.TestCase):
    def test_detect_model_runner_failure_bad_implementation(self):
        logs = "INFO\nERROR - BAD_IMPLEMENTATION\nImportError: No Inherited class found"
        result = _detect_model_runner_failure(logs)
        self.assertIsNotNone(result)
        self.assertIn("BAD_IMPLEMENTATION", result)

    def test_detect_model_runner_failure_returns_none_for_clean_logs(self):
        logs = "INFO ModelRunner started and ready to serve"
        self.assertIsNone(_detect_model_runner_failure(logs))

    def test_detect_prediction_validation_failure_marker(self):
        logs = (
            "2026-01-01 00:00:00 | node_template.services.predict_service | ERROR | "
            "INFERENCE_OUTPUT_VALIDATION_ERROR model_id=1 scope_key=btc error=missing 'expected_return'"
        )
        result = _detect_prediction_validation_failure(logs)
        self.assertIsNotNone(result)
        self.assertIn("INFERENCE_OUTPUT_VALIDATION_ERROR", result)

    def test_detect_prediction_validation_failure_returns_none_for_clean_logs(self):
        logs = "predict worker healthy"
        self.assertIsNone(_detect_prediction_validation_failure(logs))


if __name__ == "__main__":
    unittest.main()
