from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ExtensionSettings:
    scoring_function: str
    raw_input_provider: str | None
    ground_truth_resolver: str | None

    @classmethod
    def from_env(cls) -> "ExtensionSettings":
        return cls(
            scoring_function=os.getenv(
                "SCORING_FUNCTION",
                "node_template.extensions.default_callables:default_score_prediction",
            ),
            raw_input_provider=os.getenv(
                "RAW_INPUT_PROVIDER",
                "node_template.extensions.default_callables:default_provide_raw_input",
            ),
            ground_truth_resolver=os.getenv(
                "GROUND_TRUTH_RESOLVER",
                "node_template.extensions.default_callables:default_resolve_ground_truth",
            ),
        )
