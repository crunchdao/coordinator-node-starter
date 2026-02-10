import asyncio
import inspect
import unittest

from node_template.infrastructure.db.init_db import default_prediction_configs
from node_template.workers import predict_worker, report_worker, score_worker


class TestNodeTemplateRuntimeWiring(unittest.TestCase):
    def test_default_prediction_configs_are_defined(self):
        configs = default_prediction_configs()
        self.assertGreater(len(configs), 0)

        sample = configs[0]
        self.assertIn("asset", sample)
        self.assertIn("horizon", sample)
        self.assertIn("step", sample)
        self.assertIn("prediction_interval", sample)
        self.assertIn("active", sample)
        self.assertIn("order", sample)

    def test_worker_entrypoints_expose_async_main(self):
        self.assertTrue(inspect.iscoroutinefunction(predict_worker.main))
        self.assertTrue(inspect.iscoroutinefunction(score_worker.main))

    def test_report_worker_exposes_app(self):
        self.assertTrue(hasattr(report_worker, "app"))

    def test_predict_worker_build_service_callable(self):
        self.assertTrue(callable(predict_worker.build_service))


if __name__ == "__main__":
    unittest.main()
