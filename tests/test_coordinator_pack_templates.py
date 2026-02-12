import unittest

from coordinator_cli.commands.pack_templates import render_pack_templates


class TestCoordinatorPackTemplates(unittest.TestCase):
    def test_renders_default_template_set(self):
        files = render_pack_templates(
            "default",
            {
                "name": "btc-trader",
                "node_name": "crunch-node-btc-trader",
                "challenge_name": "crunch-btc-trader",
                "package_module": "crunch_btc_trader",
                "crunch_id": "starter-btc",
            },
        )

        self.assertIn("README.md", files)
        self.assertIn("SKILL.md", files)
        self.assertIn("crunch-node-btc-trader/README.md", files)
        self.assertIn("crunch-node-btc-trader/SKILL.md", files)
        self.assertIn("crunch-btc-trader/README.md", files)
        self.assertIn("crunch-btc-trader/SKILL.md", files)

        self.assertIn("crunch-node-btc-trader/Makefile", files)
        self.assertIn("crunch-node-btc-trader/Dockerfile", files)
        self.assertIn("crunch-node-btc-trader/docker-compose.yml", files)
        self.assertIn("crunch-node-btc-trader/runtime_definitions/contracts.py", files)
        self.assertIn("crunch-node-btc-trader/scripts/verify_e2e.py", files)
        self.assertIn("crunch-node-btc-trader/scripts/capture_runtime_logs.py", files)
        self.assertIn(
            "crunch-node-btc-trader/deployment/model-orchestrator-local/config/orchestrator.dev.yml",
            files,
        )
        self.assertIn(
            "crunch-node-btc-trader/deployment/model-orchestrator-local/config/models.dev.yml",
            files,
        )
        self.assertIn(
            "crunch-node-btc-trader/deployment/report-ui/config/global-settings.json",
            files,
        )
        self.assertIn("crunch-node-btc-trader/plugins/README.md", files)
        self.assertIn("crunch-node-btc-trader/extensions/README.md", files)
        self.assertIn("crunch-btc-trader/pyproject.toml", files)
        self.assertIn("crunch-btc-trader/crunch_btc_trader/tracker.py", files)
        self.assertIn(
            "crunch-btc-trader/crunch_btc_trader/examples/mean_reversion_tracker.py",
            files,
        )

        self.assertIn("crunch-node-btc-trader", files["README.md"])
        self.assertIn("make deploy", files["SKILL.md"])
        self.assertIn("starter-btc", files[
            "crunch-node-btc-trader/deployment/model-orchestrator-local/config/orchestrator.dev.yml"
        ])


if __name__ == "__main__":
    unittest.main()
