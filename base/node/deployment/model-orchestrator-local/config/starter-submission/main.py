from __future__ import annotations

from tracker import TrackerBase


class LocalStarterSubmission(TrackerBase):
    def predict(self, asset: str, horizon: int, step: int):
        return {"score": 0.5}
