from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ExtensionSettings:
    scoring_function: str
    inference_input_builder: str
    inference_output_validator: str | None
    model_score_aggregator: str | None
    leaderboard_ranker: str | None

    @classmethod
    def from_env(cls) -> "ExtensionSettings":
        return cls(
            scoring_function=os.getenv(
                "SCORING_FUNCTION",
                "node_template.extensions.default_callables:default_score_prediction",
            ),
            inference_input_builder=os.getenv(
                "INFERENCE_INPUT_BUILDER",
                "node_template.extensions.default_callables:default_build_inference_input",
            ),
            inference_output_validator=os.getenv(
                "INFERENCE_OUTPUT_VALIDATOR",
                "node_template.extensions.default_callables:default_validate_inference_output",
            ),
            model_score_aggregator=os.getenv(
                "MODEL_SCORE_AGGREGATOR",
                "node_template.extensions.default_callables:default_aggregate_model_scores",
            ),
            leaderboard_ranker=os.getenv(
                "LEADERBOARD_RANKER",
                "node_template.extensions.default_callables:default_rank_leaderboard",
            ),
        )
