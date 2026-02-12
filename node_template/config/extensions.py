from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ExtensionSettings:
    scoring_function: str

    @classmethod
    def from_env(cls) -> "ExtensionSettings":
        return cls(
            scoring_function=os.getenv(
                "SCORING_FUNCTION",
                "node_template.extensions.default_callables:default_score_prediction",
            ),
        )
