import base64
import secrets
from enum import Enum

from model_runner_client.model_concurrent_runners.model_concurrent_runner import ModelPredictResult

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from importlib.machinery import ModuleSpec
from typing import Optional

__spec__: Optional[ModuleSpec]


## Aggregate
class PredictionStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    ABSENT = "ABSENT"


@dataclass
class PredictionParams:
    asset: str
    horizon: int
    step: int


@dataclass
class PredictionScore:
    value: float | None
    success: bool
    failed_reason: str | None
    scored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Prediction:
    id: str  # unique identifier
    model_id: str
    params: PredictionParams
    status: PredictionStatus
    exec_time: float  # how long was the prediction
    distributions: list[dict] | None
    performed_at: datetime  # time of predict call
    resolvable_at: datetime  # time when the prediction is ready to be scored
    score: PredictionScore | None = None

    @staticmethod
    def generate_id(model_id: str, performed_at: datetime) -> str:
        return f"PRE_{model_id}_{performed_at.strftime('%Y%m%d_%H%M%S.%f')[:-3]}"

    @staticmethod
    def create(model_id: str, asset: str, horizon: int, step: int, model_result: ModelPredictResult, performed_at: datetime):
        return Prediction(

            id=Prediction.generate_id(model_id, performed_at),
            model_id=model_id,
            params=PredictionParams(asset, horizon, step),
            status=PredictionStatus(model_result.status.value),
            exec_time=model_result.exec_time_us,
            distributions=model_result.result,
            performed_at=performed_at,
            resolvable_at=performed_at + timedelta(seconds=horizon)
        )

    @staticmethod
    def create_absent(model_id: str, asset: str, horizon: int, step: int, performed_at: datetime):
        return Prediction(
            id=Prediction.generate_id(model_id, performed_at),
            model_id=model_id,
            params=PredictionParams(asset, horizon, step),
            status=PredictionStatus.ABSENT,
            exec_time=0.0,
            distributions=None,
            performed_at=performed_at,
            resolvable_at=performed_at + timedelta(seconds=horizon),
        )


def generate_config_id() -> str:
    raw = secrets.token_bytes(5)  # 40 bits randomness
    code = base64.b32encode(raw).decode("ascii").rstrip("=")
    return f"CFG_{code}"


@dataclass
class PredictionConfig:
    prediction_params: PredictionParams
    prediction_interval: int
    active: bool
    order: int
    id: str = field(default_factory=generate_config_id)

    @staticmethod
    def get_active_assets(configs: list["PredictionConfig"]) -> set[str]:
        return {cfg.prediction_params.asset for cfg in configs if cfg.active}


@dataclass
class GroupScheduler:
    horizon: int
    step: int
    prediction_interval: int
    assets: list[str]
    index: int = 0
    next_run: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger(__spec__.name if __spec__ else __name__))

    def should_run(self, now: datetime) -> bool:
        return now >= self.next_run

    def next_code(self, now: datetime) -> str:
        code = self.assets[self.index]
        self.index = (self.index + 1) % len(self.assets)
        self.next_run = now + timedelta(seconds=self.prediction_interval / len(self.assets))

        self.logger.debug(f"Next Run: {self.next_run.strftime("%H:%M:%S")}, Code: {self.assets[self.index]}, Horizon: {int(self.horizon / 60)}m, Step: {int(self.step / 60)}m")

        return code

    @staticmethod
    def create_group_schedulers(configs: list[PredictionConfig]) -> list["GroupScheduler"]:
        groups = GroupScheduler.group_configs(configs)
        return [
            GroupScheduler(
                horizon=h,
                step=s,
                prediction_interval=pi,
                assets=codes,
            )
            for (h, s, pi), codes in groups.items()
        ]

    @staticmethod
    def group_configs(configs):
        groups = defaultdict(list)
        for cfg in configs:
            params = cfg.prediction_params
            key = (params.horizon, params.step, cfg.prediction_interval)
            groups[key].append(params.asset)
        return groups
