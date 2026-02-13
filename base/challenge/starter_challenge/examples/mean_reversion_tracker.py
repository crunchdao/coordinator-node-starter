from __future__ import annotations

from starter_challenge.tracker import TrackerBase


class MeanReversionTracker(TrackerBase):
    """Predicts pullback after short-term overextension."""

    def predict(self, **kwargs):
        prices = _extract_prices(kwargs, getattr(self, "_latest_data", None))
        if len(prices) < 3:
            return {"value": 0.0}

        lookback = min(5, len(prices))
        window = prices[-lookback:]
        average = sum(window) / lookback
        deviation = (window[-1] - average) / max(abs(average), 1e-9)

        return {"value": -0.7 * deviation}


def _extract_prices(kwargs, latest_data):
    for key in ("prices", "series"):
        values = kwargs.get(key)
        if isinstance(values, list):
            return _to_numeric(values)

    candles = kwargs.get("candles_1m")
    if isinstance(candles, list):
        return _closes(candles)

    if isinstance(latest_data, dict) and isinstance(latest_data.get("candles_1m"), list):
        return _closes(latest_data["candles_1m"])

    return []


def _closes(candles):
    closes = []
    for row in candles:
        if not isinstance(row, dict):
            continue
        value = row.get("close")
        try:
            closes.append(float(value))
        except Exception:
            continue
    return closes


def _to_numeric(values):
    numeric = []
    for value in values:
        try:
            numeric.append(float(value))
        except Exception:
            continue
    return numeric
