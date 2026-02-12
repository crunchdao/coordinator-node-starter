from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from coordinator.entities.prediction import InputRecord


class InputRepository(ABC):
    @abstractmethod
    def save(self, record: InputRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def find(
        self,
        *,
        status: str | None = None,
        resolvable_before: datetime | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[InputRecord]:
        raise NotImplementedError
