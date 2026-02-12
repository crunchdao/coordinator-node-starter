import unittest
from pathlib import Path

from node_template.workers.report_worker import app


class TestRuntimeMigrationWiring(unittest.TestCase):
    def test_compose_uses_node_template_entrypoints(self):
        compose = Path("docker-compose.yml").read_text()

        self.assertIn("node_template.infrastructure.db.init_db", compose)
        self.assertIn("node_template.workers.predict_worker", compose)
        self.assertIn("node_template.workers.score_worker", compose)
        self.assertIn("node_template.workers.report_worker", compose)

    def test_dockerfile_copies_new_runtime_packages(self):
        dockerfile = Path("Dockerfile").read_text()

        self.assertIn("COPY coordinator_core ./coordinator_core", dockerfile)
        self.assertIn("COPY node_template ./node_template", dockerfile)

    def test_report_worker_has_legacy_compatible_routes(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/reports/leaderboard", paths)
        self.assertIn("/reports/models", paths)
        self.assertIn("/reports/models/global", paths)
        self.assertIn("/reports/models/params", paths)
        self.assertIn("/reports/predictions", paths)
        self.assertIn("/reports/feeds", paths)
        self.assertIn("/reports/feeds/tail", paths)


if __name__ == "__main__":
    unittest.main()
