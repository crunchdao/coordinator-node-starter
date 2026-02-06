from pydantic.dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional
import pandas as pd

from condorgame_backend.entities.model import Model, ModelScore


@dataclass
class DailySynthLeaderboardEntry:
    rank: int
    rank_crps: int
    miner_uid: str
    player_name: str
    model: str
    mean_prompt_score: float
    mean_crps_score: float
    n_scores: int
    asset: str
    time_length: int
    crunch_model: bool
    ratio_max_cap: float
    mean_crunch_score: Optional[float] = None
    


@dataclass
class DailySynthLeaderboard:
    id: str
    entries: list[DailySynthLeaderboardEntry]
    created_at: datetime

    @staticmethod
    def generate_id(created_at: datetime) -> str:
        return f"LBR_{created_at.strftime('%Y%m%d_%H%M%S.%f')[:-3]}"
    
    @staticmethod
    def create(df: pd.DataFrame) -> "DailySynthLeaderboard":
        """
        Create a daily leaderboard from a pre-ranked DataFrame.

        Each row in the DataFrame corresponds to one leaderboard entry.
        Ranking and aggregation are assumed to be done upstream.
        """

        required_columns = {
            "rank",
            "rank_crps",
            "miner_uid",
            "player_name",
            "model",
            "mean_prompt_score",
            "mean_crps_score",
            "mean_crunch_score",
            "n_scores",
            "asset",
            "time_length",
            "crunch_model",
            "ratio_max_cap",
        }

        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"Leaderboard DataFrame missing columns: {missing}")

        entries: list[DailySynthLeaderboardEntry] = []

        for _, row in df.iterrows():
            entries.append(
                DailySynthLeaderboardEntry(
                    rank=int(row["rank"]),
                    rank_crps=int(row["rank_crps"]),
                    miner_uid=str(row["miner_uid"]),
                    player_name=row.get("player_name"),
                    model=row.get("model"),
                    mean_prompt_score=float(row["mean_prompt_score"]),
                    mean_crps_score=float(row["mean_crps_score"]),
                    mean_crunch_score=(
                        float(row["mean_crunch_score"])
                        if pd.notna(row["mean_crunch_score"])
                        else None
                    ),
                    n_scores=int(row["n_scores"]),
                    asset=str(row["asset"]),
                    time_length=int(row["time_length"]),
                    crunch_model=bool(row["crunch_model"]),
                    ratio_max_cap=float(row["ratio_max_cap"]),
                )
            )

        created_at = datetime.now(timezone.utc)

        # Return the created leaderboard instance
        return DailySynthLeaderboard(id=DailySynthLeaderboard.generate_id(created_at), entries=entries, created_at=created_at)
