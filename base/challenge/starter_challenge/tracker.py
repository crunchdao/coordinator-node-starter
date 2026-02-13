from __future__ import annotations


class TrackerBase:
    """Base class for participant models."""

    def tick(self, data: dict) -> None:
        self._latest_data = data

    def predict(self, **kwargs):
        raise NotImplementedError("Implement predict() in challenge quickstarters/models")
