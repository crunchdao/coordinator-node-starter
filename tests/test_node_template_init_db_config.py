from __future__ import annotations

import json
import os
import tempfile
import unittest

from node_template.infrastructure.db.init_db import load_scheduled_prediction_configs


class TestNodeTemplateInitDbConfig(unittest.TestCase):
    def test_load_scheduled_prediction_configs_uses_defaults_when_env_missing(self):
        previous = os.environ.pop("SCHEDULED_PREDICTION_CONFIGS_PATH", None)
        try:
            configs = load_scheduled_prediction_configs()
            self.assertGreater(len(configs), 0)
            self.assertIn("scope_key", configs[0])
        finally:
            if previous is not None:
                os.environ["SCHEDULED_PREDICTION_CONFIGS_PATH"] = previous

    def test_load_scheduled_prediction_configs_reads_json_file_from_env(self):
        custom = [
            {
                "scope_key": "BTC-break-60s",
                "scope_template": {"asset": "BTC", "horizon_seconds": 60, "step_seconds": 60},
                "schedule": {"prediction_interval_seconds": 1, "resolve_after_seconds": 60},
                "active": True,
                "order": 1,
            }
        ]

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write(json.dumps(custom))
            path = handle.name

        previous = os.environ.get("SCHEDULED_PREDICTION_CONFIGS_PATH")
        os.environ["SCHEDULED_PREDICTION_CONFIGS_PATH"] = path

        try:
            configs = load_scheduled_prediction_configs()
            self.assertEqual(configs, custom)
        finally:
            if previous is None:
                os.environ.pop("SCHEDULED_PREDICTION_CONFIGS_PATH", None)
            else:
                os.environ["SCHEDULED_PREDICTION_CONFIGS_PATH"] = previous
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
