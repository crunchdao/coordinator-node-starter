from __future__ import annotations

from typing import Any


class TrackerBase:
    """Base class for participant models.

    Subclass this and implement ``predict()`` to compete.
    The ``tick()`` method receives market data on every feed update —
    use it to maintain internal state (indicators, history, etc.).

    The ``predict()`` signature must match the coordinator's
    ``CallMethodConfig``. The default expects::

        predict(subject="BTC", horizon_seconds=60, step_seconds=15)

    and must return a dict matching ``InferenceOutput`` (e.g. ``{"value": 0.5}``).
    """

    def tick(self, data: dict[str, Any]) -> None:
        """Receive latest market data. Override to maintain state.

        Args:
            data: Feed data dict (shape matches ``RawInput``).
        """
        self._latest_data = data

    def predict(self, subject: str, horizon_seconds: int, step_seconds: int) -> dict[str, Any]:
        """Return a prediction for the given scope.

        Args:
            subject: Asset being predicted (e.g. "BTC", "ETHUSDT").
            horizon_seconds: How far ahead to predict (seconds).
            step_seconds: Time step between predictions (seconds).

        Returns:
            Dict matching ``InferenceOutput`` fields.
            Default starter expects ``{"value": float}`` where positive
            means bullish and negative means bearish.
        """
        raise NotImplementedError("Implement predict() in your model")
