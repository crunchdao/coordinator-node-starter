import base64
import secrets
from dataclasses import field
from enum import Enum

from model_runner_client.model_concurrent_runners.model_concurrent_runner import ModelPredictResult

import logging
from collections import defaultdict
from pydantic.dataclasses import dataclass
from pydantic import Field
from datetime import datetime, timezone, timedelta

from importlib.machinery import ModuleSpec
from typing import Optional, Sequence, Iterable

from condorgame_backend.utils.times import format_seconds, DAY, HOUR, MINUTE

__spec__: Optional[ModuleSpec]
logger = logging.getLogger(__spec__.name if __spec__ else __name__)


## Aggregate
class PredictionStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    ABSENT = "ABSENT"


@dataclass(frozen=True)
class PredictionParams:
    asset: str
    horizon: int
    steps: tuple[int, ...]

    def __init__(self, asset: str, horizon: int, steps: Sequence[int]):
        object.__setattr__(self, "asset", asset)
        object.__setattr__(self, "horizon", horizon)
        object.__setattr__(self, "steps", tuple(steps))

    @staticmethod
    def label(asset: str, horizon: int, steps: Sequence[int]) -> str:
        return (
            f"{asset:<4} • {format_seconds(horizon):<3} • steps: "
            f"{', '.join(format_seconds(s) for s in steps)}"
        )

    def __str__(self) -> str:
        return self.label(self.asset, self.horizon, self.steps)


@dataclass
class PredictionScore:
    raw: float | None
    success: bool
    failed_reason: str | None
    final: float | None = None
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Prediction:
    id: str  # unique identifier
    model_id: str
    params: PredictionParams
    status: PredictionStatus
    exec_time: float  # how long was the prediction
    distributions: dict | None
    performed_at: datetime  # time of predict call
    resolvable_at: datetime  # time when the prediction is ready to be scored
    score: PredictionScore | None = None

    @staticmethod
    def generate_id(model_id: str, performed_at: datetime) -> str:
        return f"PRE_{model_id}_{performed_at.strftime('%Y%m%d_%H%M%S.%f')[:-3]}"

    @staticmethod
    def create(model_id: str, asset: str, horizon: int, steps: Sequence[int], model_result: ModelPredictResult, performed_at: datetime):
        return Prediction(

            id=Prediction.generate_id(model_id, performed_at),
            model_id=model_id,
            params=PredictionParams(asset, horizon, steps),
            status=PredictionStatus(model_result.status.value),
            exec_time=model_result.exec_time_us,
            distributions=model_result.result,
            performed_at=performed_at,
            resolvable_at=performed_at + timedelta(seconds=horizon)
        )

    @staticmethod
    def create_absent(model_id: str, asset: str, horizon: int, steps: Sequence[int], performed_at: datetime):
        return Prediction(
            id=Prediction.generate_id(model_id, performed_at),
            model_id=model_id,
            params=PredictionParams(asset, horizon, steps),
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
    id: str = Field(default_factory=generate_config_id)

    @staticmethod
    def get_active_assets(configs: list["PredictionConfig"]) -> set[str]:
        return {cfg.prediction_params.asset for cfg in configs if cfg.active}


@dataclass(slots=True)
class GroupScheduler:
    """
    GroupScheduler schedules prediction requests for a group of assets sharing the same:
      - horizon
      - steps
      - prediction_interval

    It cycles through assets in round-robin order, while tracking the last execution timestamp
    per asset to support restart/catch-up behavior.

    Typical usage
    -------------
    1) Build schedulers from configs:
        schedulers = GroupScheduler.create_group_schedulers(configs)

    2) After a restart, inject last executions loaded from storage:
        scheduler.set_last_executions([(params, performed_at), ...])

    3) In the main loop, request the next work item when due:
        params = scheduler.next(now, latest_info_dt)
        if params is not None:
            ... call predict(params) ...
            scheduler.mark_executed(params.asset, now)

    Scheduling rules
    --------------
    - next(dt, latest_info_dt) returns None if dt < next_run.
    - Assets are selected in round-robin order.
    - If the selected asset is not "ready" (latest_info_dt is not newer than the last execution),
      the scheduler advances to the next asset and returns None.
    - After each advance, next_run is updated:
        - normally: dt + per_asset_delta
        - but if the next asset is considered "late" based on its last execution time, next_run can be set to dt
          to catch up immediately.

    Notes
    -----
    - This class assumes timestamps are in UTC.
    - With slots=True, internal computed attributes must be declared as dataclass fields (e.g. _per_asset_delta).
    """

    horizon: int
    steps: tuple[int, ...]
    prediction_interval: float  # seconds for the whole group
    assets: tuple[str, ...]

    index: int = 0
    next_run: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_exec_ts: dict[str, float] = field(default_factory=dict)  # asset -> unix ts (seconds)

    _per_asset_delta: timedelta = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.assets:
            raise ValueError("assets cannot be empty")
        self._per_asset_delta = timedelta(seconds=self.prediction_interval / len(self.assets))

    def set_last_executions(self, executions: Iterable[tuple["PredictionParams", datetime]]) -> None:
        """
        executions: [(PredictionParams, datetime), ...]
        We keep only rows that match this group, then start from the least-recently executed asset.
        """
        self.last_exec_ts.clear()

        for params, dt in executions:
            if params.horizon != self.horizon:
                continue
            if tuple(params.steps) != self.steps:
                continue
            if params.asset not in self.assets:
                continue

            self.last_exec_ts[params.asset] = dt.timestamp()

        # LRU start: pick the least recently executed (or never executed => run first)
        if self.last_exec_ts:
            self.start_from_lru_asset()

    # ---------- main usage ----------
    def next(
        self,
        dt: Optional[datetime] = None,
        latest_info_dt: Optional[datetime] = None
    ) -> Optional["PredictionParams"]:
        """
        Returns the next params to run, or None if not due yet.
        """
        dt = dt or datetime.now(timezone.utc)
        if dt < self.next_run:
            return None

        asset = self.assets[self.index]

        if latest_info_dt and not self._is_ready(asset, latest_info_dt):
            self._advance_schedule(dt)
            return None

        # advance schedule (round-robin)
        self._advance_schedule(dt)

        return PredictionParams(asset=asset, horizon=self.horizon, steps=self.steps)

    def mark_executed(self, asset: str, dt: Optional[datetime] = None) -> None:
        if asset not in self.assets:
            return
        dt = dt or datetime.now(timezone.utc)
        self.last_exec_ts[asset] = dt.timestamp()

    def start_from_lru_asset(self) -> None:
        """
        Set the scheduler index to the least-recently executed asset.
        Assets missing from last_exec_ts are treated as 'never executed' and come first.
        """
        if not self.assets:
            self.index = 0
            return

        next_asset = min(self.assets, key=lambda a: self.last_exec_ts.get(a, float("-inf")))
        self.index = self.assets.index(next_asset)
        self.next_run = datetime.fromtimestamp(self.last_exec_ts[next_asset], timezone.utc) + timedelta(seconds=self.prediction_interval)

    def _advance_schedule(self, dt: datetime) -> None:
        self.index = (self.index + 1) % len(self.assets)
        dt_next_run = dt + self._per_asset_delta
        last_exec_ts = self.last_exec_ts.get(self.assets[self.index])
        if last_exec_ts:
            last_exec_dt = datetime.fromtimestamp(last_exec_ts, timezone.utc)

            next_scheduled_deadline = last_exec_dt + timedelta(seconds=self.prediction_interval)
            if next_scheduled_deadline <= dt:
                # late => catch up: run immediately
                dt_next_run = dt
            else:
                # not late = > don't run before the normal flow
                dt_next_run = max(dt_next_run, last_exec_dt + self._per_asset_delta)

        self.next_run = dt_next_run

        logger.debug(f"Next to Run: {self.next_run.strftime("%H:%M:%S")}, Params: [{PredictionParams.label(self.peek_asset(), self.horizon, self.steps)}]")

    def _is_ready(self, asset: str, latest_info_dt: Optional[datetime]) -> bool:
        last_exec = self.last_exec_ts.get(asset)
        if last_exec is None:
            return True  # never executed => allow once

        if latest_info_dt is None:
            return False  # no info => treat as outdated => skip

        return latest_info_dt.timestamp() > last_exec

    def peek_asset(self) -> str:
        return self.assets[self.index]

    # ---------- grouping ----------
    @property
    def key(self) -> tuple[int, tuple[int, ...], float]:
        return (self.horizon, self.steps, float(self.prediction_interval))

    @staticmethod
    def group_configs(configs: Iterable["PredictionConfig"]):
        groups: dict[tuple[int, tuple[int, ...], float], list[str]] = defaultdict(list)
        for cfg in configs:
            p = cfg.prediction_params
            groups[(p.horizon, tuple(p.steps), float(cfg.prediction_interval))].append(p.asset)
        return groups

    @staticmethod
    def create_group_schedulers(configs: list["PredictionConfig"]) -> list["GroupScheduler"]:
        groups = GroupScheduler.group_configs(configs)
        return [
            GroupScheduler(horizon=h, steps=steps, prediction_interval=pi, assets=tuple(assets))
            for (h, steps, pi), assets in groups.items()
        ]
