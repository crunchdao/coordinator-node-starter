import os
import unittest

from node_template.config.runtime import RuntimeSettings


class TestNodeTemplateRuntimeSettings(unittest.TestCase):
    def test_default_checkpoint_interval(self):
        settings = RuntimeSettings.from_env()
        self.assertEqual(settings.checkpoint_interval_seconds, 900)

    def test_default_model_runner_timeout_is_seconds_float(self):
        settings = RuntimeSettings.from_env()
        self.assertEqual(settings.model_runner_timeout_seconds, 60.0)

    def test_default_runtime_branding_is_generic(self):
        settings = RuntimeSettings.from_env()
        self.assertEqual(settings.crunch_id, "starter-challenge")
        self.assertEqual(settings.base_classname, "tracker.TrackerBase")

    def test_checkpoint_interval_override(self):
        previous = os.environ.get("CHECKPOINT_INTERVAL_SECONDS")
        os.environ["CHECKPOINT_INTERVAL_SECONDS"] = "123"
        try:
            settings = RuntimeSettings.from_env()
            self.assertEqual(settings.checkpoint_interval_seconds, 123)
        finally:
            if previous is None:
                os.environ.pop("CHECKPOINT_INTERVAL_SECONDS", None)
            else:
                os.environ["CHECKPOINT_INTERVAL_SECONDS"] = previous

    def test_model_runner_timeout_accepts_subsecond_values(self):
        previous = os.environ.get("MODEL_RUNNER_TIMEOUT_SECONDS")
        os.environ["MODEL_RUNNER_TIMEOUT_SECONDS"] = "0.1"
        try:
            settings = RuntimeSettings.from_env()
            self.assertEqual(settings.model_runner_timeout_seconds, 0.1)
        finally:
            if previous is None:
                os.environ.pop("MODEL_RUNNER_TIMEOUT_SECONDS", None)
            else:
                os.environ["MODEL_RUNNER_TIMEOUT_SECONDS"] = previous


if __name__ == "__main__":
    unittest.main()
