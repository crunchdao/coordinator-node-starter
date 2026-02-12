from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord
from coordinator_core.schemas import ScheduleEnvelope
from node_template.contracts import CrunchContract
from node_template.services.input_service import InputService

try:
    from model_runner_client.grpc.generated.commons_pb2 import Argument, Variant, VariantType
    from model_runner_client.model_concurrent_runners.dynamic_subclass_model_concurrent_runner import (
        DynamicSubclassModelConcurrentRunner,
    )
    from model_runner_client.utils.datatype_transformer import encode_data

    MODEL_RUNNER_PROTO_AVAILABLE = True
except Exception:  # pragma: no cover
    MODEL_RUNNER_PROTO_AVAILABLE = False


class PredictService:
    def __init__(
        self,
        checkpoint_interval_seconds: int,
        input_service: InputService,
        contract: CrunchContract | None = None,
        transform: Callable | None = None,
        model_repository=None,
        prediction_repository=None,
        runner=None,
        model_runner_node_host: str = "model-orchestrator",
        model_runner_node_port: int = 9091,
        model_runner_timeout_seconds: float = 60,
        crunch_id: str = "starter-challenge",
        base_classname: str = "tracker.TrackerBase",
        # Legacy — accepted but ignored
        raw_input_provider: Any = None,
        inference_input_builder: Any = None,
        inference_output_validator: Any = None,
        prediction_scope_builder: Any = None,
        predict_call_builder: Any = None,
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.input_service = input_service
        self.contract = contract or CrunchContract()
        self.transform = transform
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
        self._next_run_by_config_id: dict[str, datetime] = {}

        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()

    # ── public ──

    async def run(self) -> None:
        self.logger.info("predict service started")
        while not self.stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception("predict loop error: %s", exc)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.checkpoint_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def run_once(self, raw_input: dict[str, Any] | None = None, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        if raw_input is None:
            raw_input = self.input_service.get_input(now)

        await self._ensure_runner_initialized()
        await self._ensure_models_loaded()

        inference_input = self._validate_input(raw_input)

        await self._tick_models(inference_input)

        predictions = await self._run_configs(inference_input, now)
        if predictions:
            self.prediction_repository.save_all(predictions)
            self.logger.info("Saved %d predictions", len(predictions))
            return True

        self.logger.info("No predictions produced in this cycle")
        return False

    async def shutdown(self) -> None:
        self.stop_event.set()
        if self._runner_sync_task is not None:
            self._runner_sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner_sync_task

    # ── input validation ──

    def _validate_input(self, raw_input: dict[str, Any]) -> dict[str, Any]:
        raw_data = self.contract.raw_input_type(**raw_input)
        if self.transform is not None:
            transformed = self.transform(raw_data)
            return self.contract.input_type.model_validate(transformed).model_dump()
        return self.contract.input_type(**raw_data.model_dump()).model_dump()

    # ── model runner ──

    async def _ensure_runner_initialized(self) -> None:
        if self._runner is None:
            self._runner = self._build_default_runner()
        if self._runner_initialized:
            return
        await self._runner.init()
        self._runner_sync_task = asyncio.create_task(self._runner.sync())
        self._runner_initialized = True

    async def _ensure_models_loaded(self) -> None:
        if not self._known_models:
            self._known_models.update(self.model_repository.fetch_all())

    async def _tick_models(self, inference_input: dict[str, Any]) -> None:
        responses = await self._runner.call("tick", self._encode_tick(inference_input))
        for model_run, _ in responses.items():
            model = self._to_model(model_run)
            self._known_models[model.id] = model
            self.model_repository.save(model)

    # ── prediction loop ──

    async def _run_configs(self, inference_input: dict[str, Any], now: datetime) -> list[PredictionRecord]:
        configs = self._fetch_active_configs()
        if not configs:
            self.logger.info("No active prediction configs found")
            return []

        all_predictions: list[PredictionRecord] = []
        for config in configs:
            if not config.get("active", True):
                continue

            config_id = str(config.get("id") or self._config_identity(config))
            next_run = self._next_run_by_config_id.get(config_id, now)
            if now < next_run:
                continue

            predictions = await self._predict_for_config(config, inference_input, now)
            all_predictions.extend(predictions)

            schedule = self._parse_schedule(config)
            self._next_run_by_config_id[config_id] = now + timedelta(
                seconds=int(schedule.prediction_interval_seconds)
            )

        return all_predictions

    async def _predict_for_config(
        self, config: dict[str, Any], inference_input: dict[str, Any], now: datetime
    ) -> list[PredictionRecord]:
        scope = self._build_scope(config)
        scope_key = scope.get("scope_key", "default-scope")
        predict_args = self._build_predict_args(scope)

        responses = await self._runner.call("predict", predict_args)
        resolvable_at = self._compute_resolvable_at(config, now, scope)

        predictions: dict[str, PredictionRecord] = {}

        for model_run, result in responses.items():
            model = self._to_model(model_run)
            self._known_models[model.id] = model
            self.model_repository.save(model)

            status = self._extract_status(result)
            output = self._normalize_output(getattr(result, "result", {}))

            validation_error = self._validate_output(output)
            if validation_error:
                status = "FAILED"

            predictions[model.id] = self._make_prediction(
                model_id=model.id, config=config, scope_key=scope_key, scope=scope,
                status=status, output=output, validation_error=validation_error,
                inference_input=inference_input, now=now, resolvable_at=resolvable_at,
                exec_time_ms=float(getattr(result, "exec_time_us", 0.0)),
            )

        # Mark absent models
        for model_id in self._known_models:
            if model_id not in predictions:
                predictions[model_id] = self._make_prediction(
                    model_id=model_id, config=config, scope_key=scope_key, scope=scope,
                    status="ABSENT", output={}, validation_error=None,
                    inference_input=inference_input, now=now, resolvable_at=resolvable_at,
                    exec_time_ms=0.0,
                )

        return list(predictions.values())

    # ── scope & schedule ──

    def _build_scope(self, config: dict[str, Any]) -> dict[str, Any]:
        scope_data = self.contract.scope.model_dump()
        scope_data.update(config.get("scope_template") or {})
        return {
            "scope_key": str(config.get("scope_key") or "default-scope"),
            **scope_data,
        }

    def _compute_resolvable_at(self, config: dict[str, Any], now: datetime, scope: dict[str, Any]) -> datetime:
        schedule = self._parse_schedule(config)
        seconds = schedule.resolve_after_seconds
        if seconds is None:
            seconds = scope.get("horizon_seconds", self.contract.scope.horizon_seconds)
        return now + timedelta(seconds=max(0, int(seconds or 0)))

    @staticmethod
    def _parse_schedule(config: dict[str, Any]) -> ScheduleEnvelope:
        raw = config.get("schedule") if isinstance(config.get("schedule"), dict) else {}
        return ScheduleEnvelope.model_validate(raw)

    # ── prediction record ──

    def _make_prediction(
        self, *, model_id: str, config: dict[str, Any], scope_key: str,
        scope: dict[str, Any], status: str, output: dict[str, Any],
        validation_error: str | None, inference_input: dict[str, Any],
        now: datetime, resolvable_at: datetime, exec_time_ms: float,
    ) -> PredictionRecord:
        is_absent = status == "ABSENT"
        input_payload = {**inference_input, "_scope": scope}

        return PredictionRecord(
            id=self._prediction_id(model_id, now, scope_key, absent=is_absent),
            model_id=model_id,
            prediction_config_id=str(config.get("id")) if config.get("id") else None,
            scope_key=scope_key,
            scope={k: v for k, v in scope.items() if k != "scope_key"},
            status=status,
            exec_time_ms=exec_time_ms,
            inference_input=input_payload,
            inference_output=(
                {"_validation_error": validation_error, "raw_output": output}
                if validation_error
                else output
            ),
            performed_at=now,
            resolvable_at=resolvable_at,
        )

    def _validate_output(self, output: dict[str, Any]) -> str | None:
        try:
            validated = self.contract.output_type(**output)
            output.update(validated.model_dump())
            return None
        except Exception as exc:
            self.logger.error("INFERENCE_OUTPUT_VALIDATION_ERROR: %s", exc)
            return str(exc)

    # ── helpers ──

    def _fetch_active_configs(self) -> list[dict[str, Any]]:
        if hasattr(self.prediction_repository, "fetch_active_configs"):
            return list(self.prediction_repository.fetch_active_configs())
        return []

    def _build_default_runner(self):
        if not MODEL_RUNNER_PROTO_AVAILABLE:
            raise RuntimeError("model-runner-client dependency is required")
        return DynamicSubclassModelConcurrentRunner(
            host=self._runner_host, port=self._runner_port,
            crunch_id=self.crunch_id, base_classname=self.base_classname,
            timeout=self._runner_timeout,
            max_consecutive_failures=100, max_consecutive_timeouts=100,
        )

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

    @staticmethod
    def _extract_status(result) -> str:
        status = getattr(result, "status", "UNKNOWN")
        return str(status.value) if hasattr(status, "value") else str(status)

    @staticmethod
    def _normalize_output(output: Any) -> dict[str, Any]:
        return output if isinstance(output, dict) else {"result": output}

    @staticmethod
    def _prediction_id(model_id: str, now: datetime, scope_key: str, absent: bool = False) -> str:
        suffix = "ABS" if absent else "PRE"
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in scope_key)
        return f"{suffix}_{model_id}_{safe}_{now.strftime('%Y%m%d_%H%M%S.%f')[:-3]}"

    @staticmethod
    def _config_identity(config: dict[str, Any]) -> str:
        scope_key = str(config.get("scope_key") or "default-scope")
        interval = (config.get("schedule") or {}).get("prediction_interval_seconds")
        return f"{scope_key}-{interval}"

    # ── proto encoding ──

    @staticmethod
    def _encode_tick(inference_input: dict[str, Any]):
        if MODEL_RUNNER_PROTO_AVAILABLE:
            arg = Argument(
                position=1,
                data=Variant(type=VariantType.JSON, value=encode_data(VariantType.JSON, inference_input)),
            )
            return ([arg], [])
        return (inference_input,)

    def _build_predict_args(self, scope: dict[str, Any]):
        asset = scope.get("asset", self.contract.scope.asset)
        horizon = int(scope.get("horizon_seconds", self.contract.scope.horizon_seconds))
        step = int(scope.get("step_seconds", self.contract.scope.step_seconds))
        args = [asset, horizon, step]

        if MODEL_RUNNER_PROTO_AVAILABLE:
            proto_args = []
            for idx, value in enumerate(args, start=1):
                vtype, encoded = self._variant_for_value(value)
                proto_args.append(Argument(position=idx, data=Variant(type=vtype, value=encoded)))
            return (proto_args, [])
        return tuple(args)

    @staticmethod
    def _variant_for_value(value: Any):
        if isinstance(value, bool):
            return VariantType.BOOL, encode_data(VariantType.BOOL, value)
        if isinstance(value, int):
            return VariantType.INT, encode_data(VariantType.INT, value)
        if isinstance(value, float):
            return VariantType.FLOAT, encode_data(VariantType.FLOAT, value)
        if isinstance(value, str):
            return VariantType.STRING, encode_data(VariantType.STRING, value)
        return VariantType.JSON, encode_data(VariantType.JSON, value)
