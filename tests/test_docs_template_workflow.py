import unittest
from pathlib import Path


class TestDocsTemplateWorkflow(unittest.TestCase):
    REQUIRED_POINTS = [
        "Define Model Interface",
        "Define inference input",
        "Define inference output",
        "Define scoring function",
        "Define ModelScore",
        "Define checkpoint interval",
    ]

    def test_readme_describes_two_repo_model(self):
        readme = Path("README.md").read_text()
        self.assertIn("coordinator_core", readme)
        self.assertIn("node_template", readme)
        self.assertIn("crunch-<name>", readme)
        self.assertIn("crunch-node-<name>", readme)
        self.assertIn("make verify-e2e", readme)

    def test_build_guide_lists_required_definition_points(self):
        guide = Path("docs/BUILD_YOUR_OWN_CHALLENGE.md").read_text()
        for item in self.REQUIRED_POINTS:
            with self.subTest(item=item):
                self.assertIn(item, guide)


if __name__ == "__main__":
    unittest.main()
