import asyncio
import inspect
import logging
import unittest

from node_template.infrastructure.db.init_db import default_prediction_configs, tables_to_reset
from node_template.workers import predict_worker, report_worker, score_worker


class TestNodeTemplateRuntimeWiring(unittest.TestCase):
    def test_default_prediction_configs_are_defined(self):
        configs = default_prediction_configs()
        self.assertGreater(len(configs), 0)

        sample = configs[0]
        self.assertIn("scope_key", sample)
        self.assertIn("scope_template", sample)
        self.assertIn("schedule", sample)
        self.assertIn("active", sample)
        self.assertIn("order", sample)

        self.assertTrue(all(config["scope_key"] for config in configs))
        self.assertTrue(any(config["schedule"].get("prediction_interval_seconds", 0) <= 300 for config in configs))

    def test_init_db_resets_canonical_tables(self):
        tables = set(tables_to_reset())
        self.assertIn("models", tables)
        self.assertIn("predictions", tables)
        self.assertIn("model_scores", tables)
        self.assertIn("leaderboards", tables)

    def test_worker_entrypoints_expose_async_main(self):
        self.assertTrue(inspect.iscoroutinefunction(predict_worker.main))
        self.assertTrue(inspect.iscoroutinefunction(score_worker.main))

    def test_report_worker_exposes_app(self):
        self.assertTrue(hasattr(report_worker, "app"))

    def test_predict_worker_build_service_callable(self):
        self.assertTrue(callable(predict_worker.build_service))

    def test_workers_configure_info_logging(self):
        predict_worker.configure_logging()
        self.assertTrue(logging.getLogger("node_template.workers.predict_worker").isEnabledFor(logging.INFO))

        score_worker.configure_logging()
        self.assertTrue(logging.getLogger("node_template.workers.score_worker").isEnabledFor(logging.INFO))


if __name__ == "__main__":
    unittest.main()
