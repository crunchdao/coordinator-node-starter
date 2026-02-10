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
            settings.inference_input_builder,
            "node_template.extensions.default_callables:default_build_inference_input",
        )
        self.assertEqual(
            settings.inference_output_validator,
            "node_template.extensions.default_callables:default_validate_inference_output",
        )
        self.assertEqual(
            settings.model_score_aggregator,
            "node_template.extensions.default_callables:default_aggregate_model_scores",
        )
        self.assertEqual(
            settings.leaderboard_ranker,
            "node_template.extensions.default_callables:default_rank_leaderboard",
        )

    def test_default_inference_builder_callable_is_resolvable(self):
        settings = ExtensionSettings.from_env()
        fn = resolve_callable(
            settings.inference_input_builder,
            required_params=("raw_input",),
        )
        self.assertTrue(callable(fn))

    def test_default_extension_callables_are_resolvable(self):
        settings = ExtensionSettings.from_env()

        validator = resolve_callable(
            settings.inference_output_validator,
            required_params=("inference_output",),
        )
        aggregator = resolve_callable(
            settings.model_score_aggregator,
            required_params=("scored_predictions", "models"),
        )
        ranker = resolve_callable(
            settings.leaderboard_ranker,
            required_params=("entries",),
        )

        self.assertTrue(callable(validator))
        self.assertTrue(callable(aggregator))
        self.assertTrue(callable(ranker))


if __name__ == "__main__":
    unittest.main()
