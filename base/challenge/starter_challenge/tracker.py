from __future__ import annotations


class TrackerBase:
    """Base class for participant models."""

    # Replace with your own implementation
    def tick(self, data: dict) -> None:
        self._latest_data = data
        
    # Replace with your own implementation
    def predict(self, **kwargs):
        raise NotImplementedError("Implement predict() in challenge quickstarters/models")
