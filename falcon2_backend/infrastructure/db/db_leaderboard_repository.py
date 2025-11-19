from __future__ import annotations

from dataclasses import asdict

from sqlmodel import Session

from falcon2_backend.entities.leaderboard import Leaderboard
from falcon2_backend.services.interfaces.leaderboard_repository import LeaderboardRepository
from falcon2_backend.infrastructure.db.db_tables import LeaderboardRow


class DBLeaderboardRepository(LeaderboardRepository):
    """
    Simple persistence of leaderboard snapshots + entries.
    """

    def __init__(self, session: Session):
        self._session = session

    def save(self, leaderboard: Leaderboard) -> None:
        entries = [asdict(entry) for entry in leaderboard.entries]

        # Check if exists
        existing = self._session.get(LeaderboardRow, leaderboard.id)

        if existing is None:
            # INSERT
            row = LeaderboardRow(
                id=leaderboard.id,
                created_at=leaderboard.created_at,
                entries=entries,
            )
            self._session.add(row)

        else:
            # UPDATE
            existing.created_at = leaderboard.created_at
            existing.entries = entries

        self._session.commit()
