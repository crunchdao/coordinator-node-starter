from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from coordinator_core.entities.model import Model
from coordinator_core.entities.prediction import PredictionRecord

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
        inference_input_builder: Callable[[dict[str, Any]], dict[str, Any]],
        model_repository,
        prediction_repository,
        runner=None,
        model_runner_node_host: str = "model-orchestrator",
        model_runner_node_port: int = 9091,
        model_runner_timeout_seconds: int = 60,
        crunch_id: str = "condorgame",
        base_classname: str = "condorgame.tracker.TrackerBase",
    ):
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self.inference_input_builder = inference_input_builder
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
        raw_input = raw_input or {}

        await self._ensure_runner_initialized()
        await self._ensure_models_loaded()

        inference_input = self.inference_input_builder(raw_input)
        tick_responses = await self._call_runner_tick(inference_input)
        self._save_models_from_responses(tick_responses)

        created_predictions: list[PredictionRecord] = []

        for config in self._fetch_active_configs():
            if not config.get("active", True):
                continue

            config_id = str(config.get("id") or self._config_identity(config))
            next_run = self._next_run_by_config_id.get(config_id, now)
            if now < next_run:
                continue

            batch_predictions = await self._predict_for_config(config=config, inference_input=inference_input, now=now)
            created_predictions.extend(batch_predictions)

            interval = int(config.get("prediction_interval", self.checkpoint_interval_seconds))
            self._next_run_by_config_id[config_id] = now + timedelta(seconds=interval)

        if created_predictions:
            self.prediction_repository.save_all(created_predictions)
            self.logger.info("Saved %d predictions", len(created_predictions))
            return True

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

    def _fetch_active_configs(self) -> list[dict[str, Any]]:
        if hasattr(self.prediction_repository, "fetch_active_configs"):
            return list(self.prediction_repository.fetch_active_configs())

        return []

    async def _call_runner_tick(self, inference_input: dict[str, Any]):
        args = self._build_tick_args(inference_input)
        return await self._runner.call("tick", args)

    async def _predict_for_config(self, config: dict[str, Any], inference_input: dict[str, Any], now: datetime):
        asset = str(config["asset"])
        horizon = int(config["horizon"])
        step = int(config["step"])

        args = self._build_predict_args(asset=asset, horizon=horizon, step=step)
        responses = await self._runner.call("predict", args)

        predictions_by_model: dict[str, PredictionRecord] = {}
        for model_run, prediction_res in responses.items():
            model = self._to_model(model_run)
            self._known_models[model.id] = model
            self.model_repository.save(model)

            status = self._to_status(prediction_res)
            inference_output = self._normalize_output(getattr(prediction_res, "result", {}))

            inference_input_payload = dict(inference_input)
            inference_input_payload["_context"] = {
                "asset": asset,
                "horizon": horizon,
                "step": step,
            }

            predictions_by_model[model.id] = PredictionRecord(
                id=self._prediction_id(model.id, now, asset, horizon, step),
                model_id=model.id,
                asset=asset,
                horizon=horizon,
                step=step,
                status=status,
                exec_time_ms=float(getattr(prediction_res, "exec_time_us", 0.0)),
                inference_input=inference_input_payload,
                inference_output=inference_output,
                performed_at=now,
                resolvable_at=now + timedelta(seconds=horizon),
            )

        # Mark absents for known models missing in the response
        for model_id in self._known_models.keys():
            if model_id in predictions_by_model:
                continue

            inference_input_payload = dict(inference_input)
            inference_input_payload["_context"] = {
                "asset": asset,
                "horizon": horizon,
                "step": step,
            }

            predictions_by_model[model_id] = PredictionRecord(
                id=self._prediction_id(model_id, now, asset, horizon, step, absent=True),
                model_id=model_id,
                asset=asset,
                horizon=horizon,
                step=step,
                status="ABSENT",
                exec_time_ms=0.0,
                inference_input=inference_input_payload,
                inference_output={},
                performed_at=now,
                resolvable_at=now + timedelta(seconds=horizon),
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

    @staticmethod
    def _prediction_id(model_id: str, now: datetime, asset: str, horizon: int, step: int, absent: bool = False) -> str:
        suffix = "ABS" if absent else "PRE"
        return f"{suffix}_{model_id}_{asset}_{horizon}_{step}_{now.strftime('%Y%m%d_%H%M%S.%f')[:-3]}"

    @staticmethod
    def _config_identity(config: dict[str, Any]) -> str:
        return f"{config.get('asset')}-{config.get('horizon')}-{config.get('step')}-{config.get('prediction_interval')}"

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
    def _build_predict_args(asset: str, horizon: int, step: int):
        if MODEL_RUNNER_PROTO_AVAILABLE:
            asset_arg = Argument(position=1, data=Variant(type=VariantType.STRING, value=encode_data(VariantType.STRING, asset)))
            horizon_arg = Argument(position=2, data=Variant(type=VariantType.INT, value=encode_data(VariantType.INT, horizon)))
            step_arg = Argument(position=3, data=Variant(type=VariantType.INT, value=encode_data(VariantType.INT, step)))
            return ([asset_arg, horizon_arg, step_arg], [])

        return (asset, horizon, step)

