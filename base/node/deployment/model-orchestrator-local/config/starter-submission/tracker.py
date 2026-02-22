from __future__ import annotations

from typing import Any


class TrackerBase:
    """Base class for participant models.

    The ``predict()`` signature must match the coordinator's
    ``CallMethodConfig``. Default: ``predict(subject, horizon_seconds, step_seconds)``.
    """

    def tick(self, data: dict[str, Any]) -> None:
        """Receive latest market data. Override to maintain state."""
        self._latest_data = data

    def predict(self, subject: str, horizon_seconds: int, step_seconds: int) -> dict[str, Any]:
        """Return a prediction for the given scope.

        Returns:
            Dict matching ``InferenceOutput`` fields (e.g. ``{"value": 0.5}``).
        """
        raise NotImplementedError("Implement predict() in your model")
