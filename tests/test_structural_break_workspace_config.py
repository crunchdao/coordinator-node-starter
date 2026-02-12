from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


class TestStructuralBreakWorkspaceConfig(unittest.TestCase):
    def test_structural_break_stream_uses_three_pairs(self):
        path = Path(
            "crunch-implementations/structural-break-stream/"
            "crunch-node-structural-break-stream/config/scheduled_prediction_configs.json"
        )
        rows = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 3)

        assets = [row.get("scope_template", {}).get("asset") for row in rows]
        self.assertEqual(sorted(assets), ["BTC", "ETH", "SOL"])

    def test_model_orchestrator_has_five_structural_break_quickstarters(self):
        path = Path("deployment/model-orchestrator-local/config/models.dev.yml")
        content = path.read_text(encoding="utf-8")

        model_ids = re.findall(r"(?m)^\s*- id:\s*\"?([0-9]+)\"?\s*$", content)
        submission_ids = re.findall(r"(?m)^\s*submission_id:\s*([a-z0-9-]+)\s*$", content)
        crunch_ids = re.findall(r"(?m)^\s*crunch_id:\s*([a-z0-9-]+)\s*$", content)

        self.assertEqual(len(model_ids), 5)
        self.assertEqual(len(submission_ids), 5)
        self.assertEqual(len(set(submission_ids)), 5)
        self.assertTrue(all(value == "structural-break-stream" for value in crunch_ids))


if __name__ == "__main__":
    unittest.main()
