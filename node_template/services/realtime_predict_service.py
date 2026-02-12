"""Realtime predict service: time-series data, actuals resolved by time interval."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator_core.entities.prediction import PredictionRecord
from coordinator_core.schemas import ScheduleEnvelope
from node_template.services.predict_service import PredictService


class RealtimePredictService(PredictService):
    """Time-series variant: event-driven loop, actuals = data at prediction + horizon."""

    def __init__(self, checkpoint_interval_seconds: int = 60, **kwargs):
        super().__init__(**kwargs)
        self.checkpoint_interval_seconds = checkpoint_interval_seconds
        self._next_run: dict[str, datetime] = {}

    # ── main loop ──

    async def run(self) -> None:
        self.logger.info("realtime predict service started")
        while not self.stop_event.is_set():
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception("predict loop error: %s", exc)
            await self._wait_for_data()

    async def run_once(self, raw_input: dict[str, Any] | None = None, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        await self.init_runner()

        # 1. get data, send to models
        inference_input = self.validate_input(raw_input) if raw_input else self.get_data(now)
        await self.tick_models(inference_input)

        # 2. run prediction configs, store predictions
        predictions = await self._run_configs(inference_input, now)
        self.save_predictions(predictions)

        # 3. resolve actuals for past predictions
        self.resolve_actuals(now)

        return len(predictions) > 0

    # ── 3. resolve actuals (time-series) ──

    def resolve_actuals(self, now: datetime) -> int:
        """Find predictions past their horizon, look up what actually happened."""
        pending = self.prediction_repository.find_predictions(
            status="PENDING", resolvable_before=now,
        )
        if not pending:
            return 0

        resolved_count = 0
        for prediction in pending:
            scope = prediction.scope or {}
            actuals = self.input_service.get_ground_truth(
                performed_at=prediction.performed_at,
                resolvable_at=prediction.resolvable_at,
                asset=scope.get("asset"),
            )
            if actuals is None:
                continue

            self.prediction_repository.save_actuals(prediction.id, actuals)
            resolved_count += 1

        if resolved_count:
            self.logger.info("Resolved actuals for %d predictions", resolved_count)

        return resolved_count

    # ── prediction configs ──

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
            if now < self._next_run.get(config_id, now):
                continue

            predictions = await self._predict_for_config(config, inference_input, now)
            all_predictions.extend(predictions)

            schedule = self._parse_schedule(config)
            self._next_run[config_id] = now + timedelta(seconds=int(schedule.prediction_interval_seconds))

        return all_predictions

    async def _predict_for_config(
        self, config: dict[str, Any], inference_input: dict[str, Any], now: datetime,
    ) -> list[PredictionRecord]:
        scope = self._build_scope(config)
        scope_key = scope.get("scope_key", "default-scope")
        config_id = str(config.get("id")) if config.get("id") else None

        responses = await self.predict(inference_input, scope)
        resolvable_at = self._compute_resolvable_at(config, now, scope)

        predictions: dict[str, PredictionRecord] = {}

        for model_run, result in responses.items():
            model = self._to_model(model_run)
            self.register_model(model)

            runner_status = self._extract_status(result)
            output = getattr(result, "result", {})
            output = output if isinstance(output, dict) else {"result": output}

            validation_error = self.validate_output(output)
            if validation_error:
                status = "FAILED"
                output = {"_validation_error": validation_error, "raw_output": output}
            elif runner_status == "SUCCESS":
                status = "PENDING"  # awaiting actuals
            else:
                status = runner_status

            predictions[model.id] = self.make_prediction(
                model_id=model.id, scope_key=scope_key, scope=scope,
                status=status, output=output, inference_input=inference_input,
                now=now, resolvable_at=resolvable_at,
                exec_time_ms=float(getattr(result, "exec_time_us", 0.0)),
                config_id=config_id,
            )

        # Mark absent models
        for model_id in self._known_models:
            if model_id not in predictions:
                predictions[model_id] = self.make_prediction(
                    model_id=model_id, scope_key=scope_key, scope=scope,
                    status="ABSENT", output={}, inference_input=inference_input,
                    now=now, resolvable_at=resolvable_at, config_id=config_id,
                )

        return list(predictions.values())

    # ── scope & schedule ──

    def _build_scope(self, config: dict[str, Any]) -> dict[str, Any]:
        scope_data = self.contract.scope.model_dump()
        scope_data.update(config.get("scope_template") or {})
        return {"scope_key": str(config.get("scope_key") or "default-scope"), **scope_data}

    def _compute_resolvable_at(self, config: dict[str, Any], now: datetime, scope: dict[str, Any]) -> datetime:
        schedule = self._parse_schedule(config)
        seconds = schedule.resolve_after_seconds
        if seconds is None:
            seconds = scope.get("horizon_seconds", self.contract.scope.horizon_seconds)
        return now + timedelta(seconds=max(0, int(seconds or 0)))

    # ── event-driven wait ──

    async def _wait_for_data(self) -> None:
        """Wait for new market data (pg NOTIFY) or fall back to timeout."""
        try:
            from node_template.infrastructure.db.pg_notify import wait_for_notify

            notify_task = asyncio.create_task(
                wait_for_notify(timeout=float(self.checkpoint_interval_seconds))
            )
            stop_task = asyncio.create_task(self.stop_event.wait())

            done, pending = await asyncio.wait(
                {notify_task, stop_task}, return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        except Exception:
            try:
                await asyncio.wait_for(
                    self.stop_event.wait(), timeout=self.checkpoint_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    # ── helpers ──

    def _fetch_active_configs(self) -> list[dict[str, Any]]:
        if hasattr(self.prediction_repository, "fetch_active_configs"):
            return list(self.prediction_repository.fetch_active_configs())
        return []

    @staticmethod
    def _extract_status(result) -> str:
        status = getattr(result, "status", "UNKNOWN")
        return str(status.value) if hasattr(status, "value") else str(status)

    @staticmethod
    def _parse_schedule(config: dict[str, Any]) -> ScheduleEnvelope:
        raw = config.get("schedule") if isinstance(config.get("schedule"), dict) else {}
        return ScheduleEnvelope.model_validate(raw)

    @staticmethod
    def _config_identity(config: dict[str, Any]) -> str:
        scope_key = str(config.get("scope_key") or "default-scope")
        interval = (config.get("schedule") or {}).get("prediction_interval_seconds")
        return f"{scope_key}-{interval}"
