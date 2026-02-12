import unittest

from coordinator_core.cli.pack_templates import render_pack_templates


class TestStarterSubmissionTemplates(unittest.TestCase):
    def test_tracker_template_guards_non_iterable_tick_points(self):
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
        template = files[
            "crunch-node-btc-trader/deployment/model-orchestrator-local/config/starter-submission/tracker.py"
        ]
        self.assertIn("if not isinstance(points, (list, tuple))", template)
        self.assertIn("self.history.setdefault(asset, []).extend(points)", template)


if __name__ == "__main__":
    unittest.main()
