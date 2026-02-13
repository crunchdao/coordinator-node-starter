"""Base predict service: get data, store predictions, resolve actuals."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from coordinator.entities.model import Model
from coordinator.entities.prediction import InputRecord, PredictionRecord, PredictionStatus
from coordinator.db.repositories import DBInputRepository, DBModelRepository, DBPredictionRepository
from coordinator.contracts import CrunchContract
from coordinator.services.feed_reader import FeedReader

try:
    from model_runner_client.grpc.generated.commons_pb2 import Argument, Variant, VariantType
    from model_runner_client.model_concurrent_runners.dynamic_subclass_model_concurrent_runner import (
        DynamicSubclassModelConcurrentRunner,
    )
    from model_runner_client.model_concurrent_runners.model_concurrent_runner import ModelConcurrentRunner
    from model_runner_client.utils.datatype_transformer import encode_data

    MODEL_RUNNER_PROTO_AVAILABLE = True
except Exception:  # pragma: no cover
    ModelConcurrentRunner = None  # type: ignore[misc,assignment]
    MODEL_RUNNER_PROTO_AVAILABLE = False


class PredictService:
    """Base: get data → run models → store predictions → resolve actuals."""

    def __init__(
        self,
        feed_reader: FeedReader,
        contract: CrunchContract | None = None,
        transform: Callable | None = None,
        input_repository: DBInputRepository | None = None,
        model_repository: DBModelRepository | None = None,
        prediction_repository: DBPredictionRepository | None = None,
        runner: ModelConcurrentRunner | None = None,
        model_runner_node_host: str = "model-orchestrator",
        model_runner_node_port: int = 9091,
        model_runner_timeout_seconds: float = 60,
        crunch_id: str = "starter-challenge",
        base_classname: str = "tracker.TrackerBase",
        **kwargs,
    ):
        self.feed_reader = feed_reader
        self.contract = contract or CrunchContract()
        self.transform = transform
        self.input_repository = input_repository
        self.model_repository = model_repository
        self.prediction_repository = prediction_repository
        self.crunch_id = crunch_id
        self.base_classname = base_classname

        self._runner = runner
        self._runner_host = model_runner_node_host
        self._runner_port = model_runner_node_port
        self._runner_timeout = model_runner_timeout_seconds
        self._runner_initialized = False
        self._runner_sync_task = None

        self._known_models: dict[str, Model] = {}
        self.logger = logging.getLogger(type(self).__name__)
        self.stop_event = asyncio.Event()

    # ── 1. get data ──

    def get_data(self, now: datetime) -> InputRecord:
        """Fetch input, apply optional transform, save to DB."""
        raw = self.feed_reader.get_input(now)
        data = self.transform(raw) if self.transform is not None else raw

        record = InputRecord(
            id=f"INP_{now.strftime('%Y%m%d_%H%M%S.%f')[:-3]}",
            raw_data=data,
            received_at=now,
        )
        if self.input_repository is not None:
            self.input_repository.save(record)

        return record

    # ── 2. store predictions ──

    async def _call_models(self, scope: dict[str, Any]) -> dict:
        """Send predict call to model runner, return raw responses."""
        return await self._runner.call("predict", self._encode_predict(scope))

    async def _tick_models(self, inference_input: dict[str, Any]) -> None:
        """Send latest data to all models."""
        responses = await self._runner.call("tick", self._encode_tick(inference_input))
        for model_run, _ in responses.items():
            self.register_model(self._to_model(model_run))

    def _build_record(
        self, *, model_id: str, input_id: str, scope_key: str,
        scope: dict[str, Any], status: str, output: dict[str, Any],
        now: datetime, resolvable_at: datetime,
        exec_time_ms: float = 0.0, config_id: str | None = None,
    ) -> PredictionRecord:
        """Construct a PredictionRecord from model runner output."""
        suffix = "ABS" if status == PredictionStatus.ABSENT else "PRE"
        safe_key = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in scope_key)
        pred_id = f"{suffix}_{model_id}_{safe_key}_{now.strftime('%Y%m%d_%H%M%S.%f')[:-3]}"

        return PredictionRecord(
            id=pred_id, input_id=input_id, model_id=model_id,
            prediction_config_id=config_id,
            scope_key=scope_key,
            scope={k: v for k, v in scope.items() if k != "scope_key"},
            status=status, exec_time_ms=exec_time_ms,
            inference_output=output, performed_at=now, resolvable_at=resolvable_at,
        )

    def _save(self, predictions: list[PredictionRecord]) -> None:
        """Persist prediction records to the repository."""
        if predictions:
            self.prediction_repository.save_all(predictions)
            self.logger.info("Saved %d predictions", len(predictions))

    # ── runner lifecycle ──

    async def init_runner(self) -> None:
        if self._runner is None:
            if not MODEL_RUNNER_PROTO_AVAILABLE:
                raise RuntimeError("model-runner-client dependency is required")
            self._runner = DynamicSubclassModelConcurrentRunner(
                host=self._runner_host, port=self._runner_port,
                crunch_id=self.crunch_id, base_classname=self.base_classname,
                timeout=self._runner_timeout,
                max_consecutive_failures=100, max_consecutive_timeouts=100,
            )
        if not self._runner_initialized:
            await self._runner.init()
            self._runner_sync_task = asyncio.create_task(self._runner.sync())
            self._runner_initialized = True

    async def shutdown(self) -> None:
        self.stop_event.set()
        if self._runner_sync_task is not None:
            self._runner_sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner_sync_task

    # ── model management ──

    def register_model(self, model: Model) -> None:
        self._known_models[model.id] = model
        self.model_repository.save(model)

    def validate_output(self, output: dict[str, Any]) -> str | None:
        try:
            output.update(self.contract.output_type(**output).model_dump())
            return None
        except Exception as exc:
            self.logger.error("INFERENCE_OUTPUT_VALIDATION_ERROR: %s", exc)
            return str(exc)

    @staticmethod
    def _to_model(model_run) -> Model:
        infos = getattr(model_run, "infos", {}) or {}
        return Model(
            id=str(getattr(model_run, "model_id")),
            name=str(getattr(model_run, "model_name", "unknown-model")),
            player_id=str(infos.get("cruncher_id", "unknown-player")),
            player_name=str(infos.get("cruncher_name", "Unknown")),
            deployment_identifier=str(getattr(model_run, "deployment_id", "unknown-deployment")),
        )

    # ── proto encoding ──

    @staticmethod
    def _encode_tick(inference_input: dict[str, Any]) -> tuple:
        if MODEL_RUNNER_PROTO_AVAILABLE:
            return ([Argument(
                position=1,
                data=Variant(type=VariantType.JSON, value=encode_data(VariantType.JSON, inference_input)),
            )], [])
        return (inference_input,)

    def _encode_predict(self, scope: dict[str, Any]) -> tuple:
        subject = scope.get("subject", self.contract.scope.subject)
        horizon = int(scope.get("horizon_seconds", self.contract.scope.horizon_seconds))
        step = int(scope.get("step_seconds", self.contract.scope.step_seconds))

        if MODEL_RUNNER_PROTO_AVAILABLE:
            return ([
                Argument(position=1, data=Variant(type=VariantType.STRING, value=encode_data(VariantType.STRING, subject))),
                Argument(position=2, data=Variant(type=VariantType.INT, value=encode_data(VariantType.INT, horizon))),
                Argument(position=3, data=Variant(type=VariantType.INT, value=encode_data(VariantType.INT, step))),
            ], [])
        return (subject, horizon, step)
