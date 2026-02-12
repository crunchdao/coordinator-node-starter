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

    def test_default_scoring_callable_is_resolvable(self):
        settings = ExtensionSettings.from_env()

        scoring = resolve_callable(
            settings.scoring_function,
            required_params=("prediction", "ground_truth"),
        )
        self.assertTrue(callable(scoring))


if __name__ == "__main__":
    unittest.main()
