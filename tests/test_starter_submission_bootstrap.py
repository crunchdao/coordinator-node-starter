import unittest
from pathlib import Path


class TestStarterSubmissionBootstrap(unittest.TestCase):
    def test_entrypoint_bootstraps_local_starter_submission_without_import(self):
        text = Path("deployment/model-orchestrator-local/config/docker-entrypoint.sh").read_text()
        self.assertIn("starter-submission", text)
        self.assertIn("/app/data/submissions/starter-benchmarktracker", text)
        self.assertNotIn("model-orchestrator dev \\", text)


if __name__ == "__main__":
    unittest.main()
