from __future__ import annotations

from math import log, sqrt

from tracker import TrackerBase


class GaussianStepTracker(TrackerBase):
    """Simple Gaussian log-return forecaster for local starter runs."""

    def predict(self, asset: str, horizon: int, step: int):
        points = self.history.get(asset, [])
        prices = [float(price) for _, price in points if float(price) > 0]
        if len(prices) < 3 or step <= 0:
            return []

        returns = [log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
        if len(returns) < 2:
            return []

        mu = sum(returns) / len(returns)
        variance = sum((r - mu) ** 2 for r in returns) / len(returns)
        sigma = sqrt(max(variance, 1e-12))

        segments = max(1, int(horizon // step))

        return [
            {
                "step": k * step,
                "type": "mixture",
                "components": [
                    {
                        "density": {
                            "type": "builtin",
                            "name": "norm",
                            "params": {"loc": mu, "scale": sigma},
                        },
                        "weight": 1,
                    }
                ],
            }
            for k in range(1, segments + 1)
        ]
