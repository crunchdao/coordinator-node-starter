from __future__ import annotations

from dataclasses import asdict
from typing import Optional, Dict
from collections import defaultdict
from statistics import mean
from datetime import date
import pandas as pd

from sqlmodel import Session, select

from condorgame_backend.entities.daily_synth_leaderboard import DailySynthLeaderboard, DailySynthLeaderboardEntry
from condorgame_backend.services.interfaces.daily_synth_leaderboard_repository import SynthLeaderboardRepository
from condorgame_backend.infrastructure.db.db_tables import DailySynthLeaderboardRow


class DBDailySynthLeaderboardRepository(SynthLeaderboardRepository):
    """
    Simple persistence of leaderboard snapshots + entries.
    """

    def __init__(self, session: Session):
        self._session = session

    def save(self, leaderboard: DailySynthLeaderboard, day: date) -> None:
        entries = [asdict(entry) for entry in leaderboard.entries]

        # Check if exists
        existing = self._session.get(DailySynthLeaderboardRow, leaderboard.id)

        if existing is None:
            # INSERT
            row = DailySynthLeaderboardRow(
                id=leaderboard.id,
                created_at=leaderboard.created_at,
                day=day,
                entries=entries,
            )
            self._session.add(row)

        else:
            # UPDATE
            existing.created_at = leaderboard.created_at
            existing.day = day
            existing.entries = entries

        self._session.commit()

    def get_latest(self) -> Optional[DailySynthLeaderboard]:
        stmt = select(DailySynthLeaderboardRow).order_by(DailySynthLeaderboardRow.created_at.desc())
        row = self._session.exec(stmt).first()

        if row is None:
            return None

        entries = [DailySynthLeaderboardEntry(**entry) for entry in row.entries]

        return DailySynthLeaderboard(
            id=row.id,
            entries=entries,
            created_at=row.created_at
        )
    
    def get_available_days(self) -> list[date]:
        """ Return all distinct calendar days for which a leaderboard snapshot exists. """
        stmt = select(DailySynthLeaderboardRow.day).distinct().order_by(DailySynthLeaderboardRow.day)
        return list(self._session.exec(stmt).all())

    def get_avg_mean_prompt_score_per_miner(self, time_length:int) -> Dict[str, float]:
        """
        For each miner_uid, compute the average mean_prompt_score over the
        last days, using only the latest snapshot per day
        and only entries where asset == "ALL".
        """

        # Get last 3 distinct days (most recent first)
        stmt_days = (
            select(DailySynthLeaderboardRow.day)
            .distinct()
            .order_by(DailySynthLeaderboardRow.day.desc())
            .limit(7)
        )
        days = self._session.exec(stmt_days).all()

        # if len(days) < 3:
        #     return {}

        # For each day, get the latest snapshot (by created_at)
        latest_rows = []

        for d in days:
            stmt_latest = (
                select(DailySynthLeaderboardRow)
                .where(DailySynthLeaderboardRow.day == d)
                .order_by(DailySynthLeaderboardRow.created_at.desc())
                .limit(1)
            )
            row = self._session.exec(stmt_latest).first()
            if row:
                latest_rows.append(row)

        if len(latest_rows) == 0:
            return None, None, None

        leaderboard_df = pd.DataFrame()
        for row in latest_rows:
            df = pd.DataFrame(row.entries)
            df["day"] = row.day
            leaderboard_df = pd.concat([leaderboard_df, df])

        if time_length is not None:
            leaderboard_df = leaderboard_df[leaderboard_df.time_length == time_length]

        # get models present at each day
        df_value_day_count = leaderboard_df[leaderboard_df.asset=="ALL"].groupby("miner_uid")["miner_uid"].count()
        max_count_day = df_value_day_count.max()
        miner_uid_present_all_time = list(df_value_day_count[df_value_day_count == max_count_day].index)
        leaderboard_df = leaderboard_df[leaderboard_df.miner_uid.isin(miner_uid_present_all_time)]

        # Buld ID
        leaderboard_df["id"] = leaderboard_df["player_name"] + "_" + leaderboard_df["model"]

        # Subset only crunch models
        crunch_df = leaderboard_df[(leaderboard_df.crunch_model == True)]
        crunch_models_id = list(crunch_df["id"].unique())

        return leaderboard_df, crunch_df, crunch_models_id


