import json
import os
from typing import Iterable
from redis import Redis

from falcon2_backend.entities.leaderboard import Leaderboard
from falcon2_backend.entities.model import Model
from falcon2_backend.services.interfaces.snapshot_publisher import SnapshotPublisher


class RedisSnapshotPublisher(SnapshotPublisher):

    def __init__(
        self,
        host: str = os.getenv("REDIS_HOST", "localhost"),
        port: int = os.getenv("REDIS_PORT", 6379),
        leaderboard_stream: str = "leaderboard_stream",
        models_stream: str = "models_stream",
    ):
        self._redis = Redis(host=host, port=port, decode_responses=True)
        self._leaderboard_stream = leaderboard_stream
        self._models_stream = models_stream

    def publish_leaderboard(self, leaderboard: Leaderboard):
        """
        Publish the leaderboard snapshot into a Redis Stream.
        """
        payload = {
            "created_at": leaderboard.created_at.isoformat(),
            "entries": [
                {
                    "model": entry.model_id,
                    "score": {
                        "recent": entry.score.recent,
                        "steady": entry.score.steady,
                        "anchor": entry.score.anchor,
                    },
                    "rank": entry.rank,
                }
                for entry in leaderboard.entries
            ],
        }

        self._redis.xadd(
            self._leaderboard_stream,
            {"data": json.dumps(payload)},
        )

    def publish_models(self, models: Iterable[Model]):
        """
        Publish a list of models as a snapshot into another Redis Stream.
        """
        array = [
            {
                "crunch_identifier": model.crunch_identifier,
                "name": model.name,
                "player": {
                    "crunch_identifier": model.player.crunch_identifier,
                    "name": model.player.name,
                },
                "overall_score": {
                    "recent": model.overall_score.recent,
                    "steady": model.overall_score.steady,
                    "anchor": model.overall_score.anchor,
                },
                "scores_by_param": [
                    {
                        "params": {
                            "asset": sbp.param.asset,
                            "horizon": sbp.param.horizon,
                            "step": sbp.param.step,
                        },
                        "score": {
                            "recent": sbp.score.recent,
                            "steady": sbp.score.steady,
                            "anchor": sbp.score.anchor,
                        },
                    }
                    for sbp in model.scores_by_param
                ],
            }
            for model in models
        ]
        payload = json.dumps(array)

        self._redis.xadd(
            self._models_stream,
            {"data": payload},
        )
