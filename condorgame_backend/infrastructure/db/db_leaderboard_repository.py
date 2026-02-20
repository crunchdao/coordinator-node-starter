from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from sqlmodel import Session, select

from condorgame_backend.entities.leaderboard import Leaderboard, LeaderboardEntry
from condorgame_backend.services.interfaces.leaderboard_repository import LeaderboardRepository
from condorgame_backend.infrastructure.db.db_tables import LeaderboardRow


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

    def get_latest(self) -> Optional[Leaderboard]:
        stmt = select(LeaderboardRow).order_by(LeaderboardRow.created_at.desc()).limit(1)
        row = self._session.exec(stmt).first()

        if row is None:
            return None

        entries = [LeaderboardEntry(**entry) for entry in row.entries]

        return Leaderboard(
            id=row.id,
            entries=entries,
            created_at=row.created_at
        )
