from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord
from coordinator_core.schemas import PredictionScopeEnvelope, ScheduleEnvelope
from node_template.contracts import CrunchContract

try:
    from model_runner_client.grpc.generated.commons_pb2 import Argument, Variant, VariantType
    from model_runner_client.model_concurrent_runners.dynamic_subclass_model_concurrent_runner import (
        DynamicSubclassModelConcurrentRunner,
    )
    from model_runner_client.utils.datatype_transformer import encode_data

    MODEL_RUNNER_PROTO_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when dependency missing
    MODEL_RUNNER_PROTO_AVAILABLE = False


class PredictService:
    def __init__(
        self,
        checkpoint_interval_seconds: int,
        raw_input_provider: Callable[[datetime], dict[str, Any]] | None,
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
        # Legacy params — ignored but accepted for backward compat
        inference_input_builder: Any = None,
        inference_output_validator: Any = None,
        prediction_scope_builder: Any = None,
        predict_call_builder: Any = None,
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.raw_input_provider = raw_input_provider
        self.contract = contract or CrunchContract()
        self.transform = transform
        self.model_repository = model_repository
        self.prediction_repository = prediction_repository

        self.model_runner_node_host = model_runner_node_host
        self.model_runner_node_port = model_runner_node_port
        self.model_runner_timeout_seconds = model_runner_timeout_seconds
        self.crunch_id = crunch_id
        self.base_classname = base_classname

        self._runner = runner
        self._runner_initialized = False
        self._runner_sync_task = None

        self._known_models: dict[str, Model] = {}
        self._next_run_by_config_id: dict[str, datetime] = {}

        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self.logger.info("node_template predict service started")

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
            raw_input = self._provide_raw_input(now)

        await self._ensure_runner_initialized()
        await self._ensure_models_loaded()

        # Validate market data via contract, then optionally transform
        market_data = self.contract.market_input_type(**raw_input)
        if self.transform is not None:
            transformed = self.transform(market_data)
            inference_input = self.contract.input_type.model_validate(transformed).model_dump()
        else:
            inference_input = self.contract.input_type(**market_data.model_dump()).model_dump()
        tick_responses = await self._call_runner_tick(inference_input)
        self._save_models_from_responses(tick_responses)

        created_predictions: list[PredictionRecord] = []
        active_configs = self._fetch_active_configs()

        if not active_configs:
            self.logger.info("No active prediction configs found")

        for config in active_configs:
            if not config.get("active", True):
                continue

            config_id = str(config.get("id") or self._config_identity(config))
            next_run = self._next_run_by_config_id.get(config_id, now)
            if now < next_run:
                continue

            batch_predictions = await self._predict_for_config(config=config, inference_input=inference_input, now=now)
            created_predictions.extend(batch_predictions)

            schedule_dict = config.get("schedule") if isinstance(config.get("schedule"), dict) else {}
            schedule = ScheduleEnvelope.model_validate(schedule_dict)
            interval = int(schedule.prediction_interval_seconds)
            self._next_run_by_config_id[config_id] = now + timedelta(seconds=interval)

        if created_predictions:
            self.prediction_repository.save_all(created_predictions)
            self.logger.info("Saved %d predictions", len(created_predictions))
            return True

        self.logger.info("No predictions produced in this cycle")
        return False

    async def shutdown(self) -> None:
        self.stop_event.set()

        if self._runner_sync_task is not None:
            self._runner_sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._runner_sync_task

    async def _ensure_runner_initialized(self) -> None:
        if self._runner is None:
            self._runner = self._build_default_runner()

        if self._runner_initialized:
            return

        await self._runner.init()
        self._runner_sync_task = asyncio.create_task(self._runner.sync())
        self._runner_initialized = True

    async def _ensure_models_loaded(self) -> None:
        if self._known_models:
            return

        existing = self.model_repository.fetch_all()
        self._known_models.update(existing)

    def _provide_raw_input(self, now: datetime) -> dict[str, Any]:
        if self.raw_input_provider is None:
            return {}

        payload = self.raw_input_provider(now)
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise ValueError("raw_input_provider must return a dictionary")
        return payload

    def _fetch_active_configs(self) -> list[dict[str, Any]]:
        if hasattr(self.prediction_repository, "fetch_active_configs"):
            return list(self.prediction_repository.fetch_active_configs())

        return []

    async def _call_runner_tick(self, inference_input: dict[str, Any]):
        args = self._build_tick_args(inference_input)
        return await self._runner.call("tick", args)

    async def _predict_for_config(self, config: dict[str, Any], inference_input: dict[str, Any], now: datetime):
        scope_object = self._build_scope(config=config)
        scope_key = str(scope_object.get("scope_key") or config.get("scope_key") or "default-scope")

        call_spec = self._build_predict_call(config=config, scope=scope_object)
        args = self._build_predict_args(call_spec)

        responses = await self._runner.call("predict", args)
        resolvable_at = self._resolve_resolvable_at(config=config, now=now, scope=scope_object)

        predictions_by_model: dict[str, PredictionRecord] = {}
        for model_run, prediction_res in responses.items():
            model = self._to_model(model_run)
            self._known_models[model.id] = model
            self.model_repository.save(model)

            status = self._to_status(prediction_res)
            inference_output = self._normalize_output(getattr(prediction_res, "result", {}))

            validation_error: str | None = None
            try:
                # Validate output via contract type
                validated = self.contract.output_type(**inference_output)
                inference_output = validated.model_dump()
            except Exception as exc:
                validation_error = str(exc)
                status = "FAILED"
                self.logger.error(
                    "INFERENCE_OUTPUT_VALIDATION_ERROR model_id=%s scope_key=%s error=%s raw_output=%s",
                    model.id,
                    scope_key,
                    validation_error,
                    inference_output,
                )

            inference_input_payload = dict(inference_input)
            inference_input_payload["_scope"] = scope_object

            predictions_by_model[model.id] = PredictionRecord(
                id=self._prediction_id(model.id, now, scope_key),
                model_id=model.id,
                prediction_config_id=str(config.get("id")) if config.get("id") else None,
                scope_key=scope_key,
                scope=dict(scope_object.get("scope") or {}),
                status=status,
                exec_time_ms=float(getattr(prediction_res, "exec_time_us", 0.0)),
                inference_input=inference_input_payload,
                inference_output=(
                    {"_validation_error": validation_error, "raw_output": inference_output}
                    if validation_error
                    else inference_output
                ),
                performed_at=now,
                resolvable_at=resolvable_at,
            )

        for model_id in self._known_models.keys():
            if model_id in predictions_by_model:
                continue

            inference_input_payload = dict(inference_input)
            inference_input_payload["_scope"] = scope_object

            predictions_by_model[model_id] = PredictionRecord(
                id=self._prediction_id(model_id, now, scope_key, absent=True),
                model_id=model_id,
                prediction_config_id=str(config.get("id")) if config.get("id") else None,
                scope_key=scope_key,
                scope=dict(scope_object.get("scope") or {}),
                status="ABSENT",
                exec_time_ms=0.0,
                inference_input=inference_input_payload,
                inference_output={},
                performed_at=now,
                resolvable_at=resolvable_at,
            )

        return list(predictions_by_model.values())

    def _save_models_from_responses(self, responses) -> None:
        for model_run, _ in responses.items():
            model = self._to_model(model_run)
            self._known_models[model.id] = model
            self.model_repository.save(model)

    def _build_default_runner(self):
        if not MODEL_RUNNER_PROTO_AVAILABLE:
            raise RuntimeError("model-runner-client dependency is required to build default runner")

        return DynamicSubclassModelConcurrentRunner(
            host=self.model_runner_node_host,
            port=self.model_runner_node_port,
            crunch_id=self.crunch_id,
            base_classname=self.base_classname,
            timeout=self.model_runner_timeout_seconds,
            max_consecutive_failures=100,
            max_consecutive_timeouts=100,
        )

    @staticmethod
    def _to_model(model_run) -> Model:
        player_id = (getattr(model_run, "infos", {}) or {}).get("cruncher_id", "unknown-player")
        player_name = (getattr(model_run, "infos", {}) or {}).get("cruncher_name", "Unknown")

        return Model(
            id=str(getattr(model_run, "model_id")),
            name=str(getattr(model_run, "model_name", "unknown-model")),
            player_id=str(player_id),
            player_name=str(player_name),
            deployment_identifier=str(getattr(model_run, "deployment_id", "unknown-deployment")),
        )

    @staticmethod
    def _to_status(prediction_res) -> str:
        status = getattr(prediction_res, "status", "UNKNOWN")
        if hasattr(status, "value"):
            return str(status.value)
        return str(status)

    @staticmethod
    def _normalize_output(output: Any) -> dict[str, Any]:
        if isinstance(output, dict):
            return output
        return {"result": output}

    def _build_scope(self, config: dict[str, Any]) -> dict[str, Any]:
        """Build prediction scope from contract + config schedule key."""
        scope_data = self.contract.scope.model_dump()
        # Allow schedule config to override scope fields
        scope_template = config.get("scope_template") or {}
        scope_data.update(scope_template)

        envelope = PredictionScopeEnvelope.model_validate(
            {
                "scope_key": str(config.get("scope_key") or "default-scope"),
                "scope": scope_data,
            }
        )
        return envelope.model_dump()

    def _build_predict_call(self, config: dict[str, Any], scope: dict[str, Any]) -> dict[str, Any]:
        """Build model predict invocation args from contract scope."""
        scope_payload = scope.get("scope") if isinstance(scope, dict) else {}
        if not isinstance(scope_payload, dict):
            scope_payload = {}

        contract_scope = self.contract.scope
        asset = scope_payload.get("asset", contract_scope.asset)
        horizon = int(scope_payload.get("horizon_seconds", contract_scope.horizon_seconds))
        step = int(scope_payload.get("step_seconds", contract_scope.step_seconds))

        return {
            "args": [asset, horizon, step],
            "kwargs": {},
        }

    @staticmethod
    def _resolve_resolvable_at(config: dict[str, Any], now: datetime, scope: dict[str, Any]) -> datetime:
        schedule_dict = config.get("schedule") if isinstance(config.get("schedule"), dict) else {}
        schedule = ScheduleEnvelope.model_validate(schedule_dict)
        resolve_after = schedule.resolve_after_seconds

        if resolve_after is None:
            scope_payload = scope.get("scope") if isinstance(scope, dict) else {}
            if isinstance(scope_payload, dict):
                resolve_after = scope_payload.get("horizon", scope_payload.get("horizon_seconds", 0))

        try:
            seconds = int(resolve_after or 0)
        except Exception:
            seconds = 0

        return now + timedelta(seconds=max(0, seconds))

    @staticmethod
    def _prediction_id(model_id: str, now: datetime, scope_key: str, absent: bool = False) -> str:
        suffix = "ABS" if absent else "PRE"
        safe_scope_key = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in scope_key)
        return f"{suffix}_{model_id}_{safe_scope_key}_{now.strftime('%Y%m%d_%H%M%S.%f')[:-3]}"

    @staticmethod
    def _config_identity(config: dict[str, Any]) -> str:
        scope_key = str(config.get("scope_key") or "default-scope")
        schedule = config.get("schedule") if isinstance(config.get("schedule"), dict) else {}
        interval = schedule.get("prediction_interval_seconds")
        return f"{scope_key}-{interval}"

    @staticmethod
    def _build_tick_args(inference_input: dict[str, Any]):
        if MODEL_RUNNER_PROTO_AVAILABLE:
            arg = Argument(
                position=1,
                data=Variant(type=VariantType.JSON, value=encode_data(VariantType.JSON, inference_input)),
            )
            return ([arg], [])

        return (inference_input,)

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

    @classmethod
    def _build_predict_args(cls, call_spec: dict[str, Any]):
        args = list(call_spec.get("args") or [])

        if MODEL_RUNNER_PROTO_AVAILABLE:
            proto_args = []
            for idx, value in enumerate(args, start=1):
                variant_type, encoded = cls._variant_for_value(value)
                proto_args.append(
                    Argument(
                        position=idx,
                        data=Variant(type=variant_type, value=encoded),
                    )
                )
            return (proto_args, [])

        return tuple(args)
