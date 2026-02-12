import unittest

from node_template.config.extensions import ExtensionSettings
from node_template.extensions.callable_resolver import resolve_callable


class TestCallableResolver(unittest.TestCase):
    def test_resolve_callable_with_signature_check(self):
        fn = resolve_callable(
            "node_template.extensions.default_callables:default_score_prediction",
            required_params=("prediction", "ground_truth"),
        )
        self.assertTrue(callable(fn))

    def test_reject_callable_with_wrong_signature(self):
        with self.assertRaises(ValueError):
            resolve_callable(
                "node_template.extensions.default_callables:invalid_score_prediction",
                required_params=("prediction", "ground_truth"),
            )

    def test_extension_settings_defaults(self):
        settings = ExtensionSettings.from_env()
        self.assertEqual(
            settings.scoring_function,
            "node_template.extensions.default_callables:default_score_prediction",
        )
        self.assertEqual(
            settings.raw_input_provider,
            "node_template.extensions.default_callables:default_provide_raw_input",
        )
        self.assertEqual(
            settings.ground_truth_resolver,
            "node_template.extensions.default_callables:default_resolve_ground_truth",
        )

    def test_default_tier1_callables_are_resolvable(self):
        settings = ExtensionSettings.from_env()

        scoring = resolve_callable(
            settings.scoring_function,
            required_params=("prediction", "ground_truth"),
        )
        raw_input_provider = resolve_callable(
            settings.raw_input_provider,
            required_params=("now",),
        )
        ground_truth_resolver = resolve_callable(
            settings.ground_truth_resolver,
            required_params=("prediction",),
        )

        self.assertTrue(callable(scoring))
        self.assertTrue(callable(raw_input_provider))
        self.assertTrue(callable(ground_truth_resolver))


if __name__ == "__main__":
    unittest.main()
