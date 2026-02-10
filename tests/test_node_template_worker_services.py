import unittest

from node_template.services.predict_service import PredictService
from node_template.services.score_service import ScoreService
from node_template.workers import predict_worker, score_worker


class TestNodeTemplateWorkerServices(unittest.TestCase):
    def test_predict_worker_builds_predict_service(self):
        service = predict_worker.build_service()
        self.assertIsInstance(service, PredictService)
        self.assertGreater(service.checkpoint_interval_seconds, 0)

    def test_score_worker_builds_score_service(self):
        service = score_worker.build_service()
        self.assertIsInstance(service, ScoreService)
        self.assertGreater(service.checkpoint_interval_seconds, 0)


if __name__ == "__main__":
    unittest.main()
