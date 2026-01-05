from pydantic.dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from condorgame_backend.entities.model import Model, ModelScore


@dataclass
class LeaderboardEntry:
    rank: int
    model_id: str
    score: ModelScore
    model_name: Optional[str] = None
    player_name: Optional[str] = None


@dataclass
class Leaderboard:
    id: str
    entries: list[LeaderboardEntry]
    created_at: datetime

    @staticmethod
    def generate_id(created_at: datetime) -> str:
        return f"LBR_{created_at.strftime('%Y%m%d_%H%M%S.%f')[:-3]}"

    @staticmethod
    def create(models: Iterable[Model]) -> "Leaderboard":
        """
        Filters, sorts models based on ranking logic and generates leaderboards.

        Models are sorted in descending order based on their scores. The scores
        are ordered by the following priority: anchor, steady, and recent.
        Leaderboard entries are then created with ranks corresponding to
        their position in the sorted list.
        """
        # Filter and sort models based on the ranking logic
        sorted_models = sorted(
            models,
            key=lambda model: (
                model.overall_score.anchor if model.overall_score and model.overall_score.anchor is not None else float('-inf'),
                model.overall_score.steady if model.overall_score and model.overall_score.steady else float('-inf'),
                model.overall_score.recent if model.overall_score and model.overall_score.recent else float('-inf'),
            ),
            reverse=True  # Sort in descending order
        )

        # Generate leaderboard entries with ranks
        entries = [
            LeaderboardEntry(rank=index + 1, model_id=model.crunch_identifier, score=model.overall_score, model_name=model.name, player_name=model.player.name)
            for index, model in enumerate(sorted_models)
        ]

        created_at = datetime.now(timezone.utc)

        # Return the created leaderboard instance
        return Leaderboard(id=Leaderboard.generate_id(created_at), entries=entries, created_at=created_at)
