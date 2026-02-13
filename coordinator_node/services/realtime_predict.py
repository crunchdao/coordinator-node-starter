"""Realtime predict service: event-driven loop, config-based scheduling."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator_node.entities.prediction import InputRecord, PredictionRecord, PredictionStatus
from coordinator_node.schemas import ScheduleEnvelope
from coordinator_node.services.predict import PredictService


class RealtimePredictService(PredictService):

    def __init__(self, checkpoint_interval_seconds: int = 60, **kwargs: Any) -> None:
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

        # 1. get data → tick models
        if raw_input is not None:
            data = self.transform(raw_input) if self.transform is not None else raw_input
            inp = InputRecord(
                id=f"INP_{now.strftime('%Y%m%d_%H%M%S.%f')[:-3]}",
                raw_data=data,
                received_at=now,
            )
        else:
            inp = self.get_data(now)
        await self._tick_models(inp.raw_data)

        # 2. run configs → build records → save
        predictions = await self._predict_all_configs(inp, now)
        self._save(predictions)
        return len(predictions) > 0

    # ── predict across configs ──

    async def _predict_all_configs(self, inp: InputRecord, now: datetime) -> list[PredictionRecord]:
        configs = self._fetch_active_configs()
        if not configs:
            self.logger.info("No active prediction configs found")
            return []

        all_predictions: list[PredictionRecord] = []

        for config in configs:
            if not config.get("active", True):
                continue

            schedule = ScheduleEnvelope.model_validate(config.get("schedule") or {})
            config_id = str(config.get("id") or self._config_key(config))

            if now < self._next_run.get(config_id, now):
                continue

            # scope + timing
            scope = {
                "scope_key": str(config.get("scope_key") or "default-scope"),
                **self.contract.scope.model_dump(),
                **(config.get("scope_template") or {}),
            }
            scope_key = scope["scope_key"]
            resolve_seconds = schedule.resolve_after_seconds
            if resolve_seconds is None:
                resolve_seconds = scope.get("horizon_seconds", self.contract.scope.horizon_seconds)
            resolvable_at = now + timedelta(seconds=max(0, int(resolve_seconds or 0)))

            # set resolvable_at on input (earliest horizon wins)
            if inp.resolvable_at is None or resolvable_at < inp.resolvable_at:
                inp.resolvable_at = resolvable_at
                # Include feed dimensions so score worker can query matching records
                feed_dims = {}
                if self.feed_reader is not None:
                    feed_dims = {
                        "source": self.feed_reader.source,
                        "subject": self.feed_reader.subject,
                        "kind": self.feed_reader.kind,
                        "granularity": self.feed_reader.granularity,
                    }
                inp.scope = {
                    **feed_dims,
                    **{k: v for k, v in scope.items() if k != "scope_key"},
                }
                if self.input_repository is not None:
                    self.input_repository.save(inp)

            # call models
            responses = await self._call_models(scope)
            seen: set[str] = set()

            for model_run, result in responses.items():
                model = self._to_model(model_run)
                self.register_model(model)
                seen.add(model.id)

                raw_status = getattr(result, "status", "UNKNOWN")
                runner_status = str(raw_status.value) if hasattr(raw_status, "value") else str(raw_status)

                output = getattr(result, "result", {})
                output = output if isinstance(output, dict) else {"result": output}

                validation_error = self.validate_output(output)
                if validation_error:
                    status = PredictionStatus.FAILED
                    output = {"_validation_error": validation_error, "raw_output": output}
                elif runner_status == "SUCCESS":
                    status = PredictionStatus.PENDING
                else:
                    status = PredictionStatus(runner_status) if runner_status in PredictionStatus.__members__ else PredictionStatus.FAILED

                all_predictions.append(self._build_record(
                    model_id=model.id, input_id=inp.id, scope_key=scope_key,
                    scope=scope, status=status, output=output,
                    now=now, resolvable_at=resolvable_at,
                    exec_time_ms=float(getattr(result, "exec_time_us", 0.0)),
                    config_id=config_id,
                ))

            # absent models
            for model_id in self._known_models:
                if model_id not in seen:
                    all_predictions.append(self._build_record(
                        model_id=model_id, input_id=inp.id, scope_key=scope_key,
                        scope=scope, status=PredictionStatus.ABSENT, output={},
                        now=now, resolvable_at=resolvable_at, config_id=config_id,
                    ))

            self._next_run[config_id] = now + timedelta(seconds=int(schedule.prediction_interval_seconds))

        return all_predictions

    # ── event-driven wait ──

    async def _wait_for_data(self) -> None:
        """Wait for pg NOTIFY or fall back to polling timeout."""
        timeout = float(self.checkpoint_interval_seconds)
        try:
            from coordinator_node.db.pg_notify import wait_for_notify
            await self._race_stop(wait_for_notify(timeout=timeout))
        except Exception:
            await self._race_stop(asyncio.sleep(timeout))

    async def _race_stop(self, coro: Any) -> None:
        """Run coro until it completes or stop_event fires."""
        task = asyncio.create_task(coro)
        stop = asyncio.create_task(self.stop_event.wait())
        done, pending = await asyncio.wait({task, stop}, return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()
            try:
                await p
            except (asyncio.CancelledError, Exception):
                pass

    # ── helpers ──

    def _fetch_active_configs(self) -> list[dict[str, Any]]:
        if hasattr(self.prediction_repository, "fetch_active_configs"):
            return list(self.prediction_repository.fetch_active_configs())
        return []

    @staticmethod
    def _config_key(config: dict[str, Any]) -> str:
        scope_key = str(config.get("scope_key") or "default-scope")
        interval = (config.get("schedule") or {}).get("prediction_interval_seconds")
        return f"{scope_key}-{interval}"
