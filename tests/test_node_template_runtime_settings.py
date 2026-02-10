import os
import unittest

from node_template.config.runtime import RuntimeSettings


class TestNodeTemplateRuntimeSettings(unittest.TestCase):
    def test_default_checkpoint_interval(self):
        settings = RuntimeSettings.from_env()
        self.assertEqual(settings.checkpoint_interval_seconds, 900)

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


if __name__ == "__main__":
    unittest.main()
