import unittest

from coordinator_core.cli.scaffold_render import (
    ensure_no_legacy_references,
    render_template_strict,
)


class TestCoordinatorCliScaffoldRenderer(unittest.TestCase):
    def test_render_template_strict_requires_all_keys(self):
        with self.assertRaises(ValueError) as ctx:
            render_template_strict("hello {name} from {place}", {"name": "alice"})

        self.assertIn("Missing template key", str(ctx.exception))
        self.assertIn("place", str(ctx.exception))

    def test_ensure_no_legacy_references_rejects_banned_tokens(self):
        with self.assertRaises(ValueError) as ctx:
            ensure_no_legacy_references(
                {
                    "README.md": "ok",
                    "config/callables.env": "MODEL_SCORE_AGGREGATOR=node_template.extensions.default_callables:default_aggregate_model_scores",
                }
            )

        self.assertIn("node_template", str(ctx.exception))
        self.assertIn("config/callables.env", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
