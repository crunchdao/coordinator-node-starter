import asyncio
import logging
import os
import signal

from model_runner_client.grpc.generated.commons_pb2 import Argument, Variant, VariantType
from model_runner_client.model_concurrent_runners.model_concurrent_runner import ModelPredictResult
from model_runner_client.utils.datatype_transformer import encode_data

from falcon2_backend.entities.model import Model
from falcon2_backend.entities.prediction import Prediction, GroupScheduler, PredictionConfig, logger
from falcon2_backend.infrastructure.memory.prices_cache import PriceStore
from falcon2_backend.services.interfaces.model_repository import ModelRepository
from falcon2_backend.services.interfaces.prediction_repository import PredictionRepository
from falcon2_backend.services.interfaces.price_repository import PriceRepository
from datetime import datetime, timedelta, timezone

from model_runner_client.model_concurrent_runners.dynamic_subclass_model_concurrent_runner import (
    DynamicSubclassModelConcurrentRunner,
)

from importlib.machinery import ModuleSpec
from typing import Optional

__spec__: Optional[ModuleSpec]


class PredictService:
    PRICE_FREQUENCY = 60  # seconds
    PRICES_HISTORY_PERIOD = timedelta(days=30)
    PRICE_RESOLUTION = "minute"

    MODEL_RUNNER_TIMEOUT = 60
    MODEL_RUNNER_NODE_HOST = os.getenv("MODEL_RUNNER_NODE_HOST", 'localhost')
    MODEL_RUNNER_NODE_PORT = os.getenv("MODEL_RUNNER_NODE_PORT", 9091)

    def __init__(self,
                 prices_repository: PriceRepository,
                 model_repository: ModelRepository,
                 prediction_repository: PredictionRepository):

        self.prices_repository = prices_repository
        self.model_repository = model_repository
        self.prediction_repository = prediction_repository

        self.logger = logging.getLogger(__spec__.name if __spec__ else __name__)

        self._init_asset_configs()
        self._init_prices_cache()
        self._init_model_runner()

        # load all the models participating
        self.game_models = self.model_repository.fetch_all()

        # Handle graceful shutdown on receiving termination signals
        self.stop_predicting_event = asyncio.Event()
        self._is_shutdown = False

    async def init(self):
        await self.model_concurrent_runner.init()

    async def run(self):
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown()))

        self.logger.info("run")
        try:
            await self.init()
            await asyncio.gather(self._run_predictions(), self._run_model_runner())
        except asyncio.CancelledError:
            self.logger.info("CancelledError")
        except Exception as e:
            self.logger.exception(e)
        finally:
            await self.shutdown()
            self.logger.info("run finished")

    async def _run_predictions(self):

        # We provide to all the models connected historical prices
        await self._tick(self.prices_cache.get_bulk(), initial=True)

        while not self.stop_predicting_event.is_set():
            now = datetime.now(timezone.utc)

            # TODO check >= because always return value
            prices = self._update_prices()
            if prices and any(prices.values()):
                await self._tick(prices)

            for scheduler in self.asset_group_schedulers:
                if scheduler.should_run(now):
                    await self._predict(scheduler.next_code(now), scheduler.horizon, scheduler.step)

            end_time = datetime.now(timezone.utc)

            sleep_duration = max(self.PRICE_FREQUENCY - (end_time - now).total_seconds(), 0)
            try:
                self.logger.debug(f"Sleeping for {int(sleep_duration)} seconds")
                await asyncio.wait_for(self.stop_predicting_event.wait(), timeout=sleep_duration)
            except asyncio.TimeoutError:
                pass

    async def _run_model_runner(self):
        return await self.model_concurrent_runner.sync()

    async def shutdown(self):
        if self._is_shutdown:
            return

        self.logger.info("shutdown")
        self.stop_predicting_event.set()

        if self.model_concurrent_runner:
            # todo change once model_runner has method to close properly
            await self.model_concurrent_runner.model_cluster.ws_client.disconnect()
            del self.model_concurrent_runner

        self._is_shutdown = True

    async def _tick(self, prices, initial=False):
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug("Tick with prices (%d values) %s", sum(len(v) for v in prices.values()), "" if initial else prices)

        model_responses = await self._prepare_and_call_tick(prices)

        # maybe should we retry in the next tick the timed out or failed?

        new_model_joining, model_changed_deployment = await self._update_game_models(model_responses)

        if not initial and (new_model_joining or model_changed_deployment):
            self.logger.debug(
                "Call tick again to send historical prices to newly joined models (%d) and models with updated deployments (%d)",
                len(new_model_joining),
                len(model_changed_deployment),
            )
            # TODO: Improve this once we have a callback from the model_runner_client library.
            await self._prepare_and_call_tick(self.prices_cache.get_bulk(),
                                              model_runs=list(new_model_joining.values()) + list(model_changed_deployment.values()))

    async def _prepare_and_call_tick(self, prices, model_runs=None):
        prices_arg = Argument(
            position=1,
            data=Variant(
                type=VariantType.JSON,
                value=encode_data(VariantType.JSON, prices),
            ),
        )

        args = ([prices_arg], [])

        model_responses = await self.model_concurrent_runner.call("tick", args, model_runs=model_runs)

        success, failed, timed_out = 0, 0, 0
        for model_runner, tick_res in model_responses.items():
            success += 1 if tick_res.status == ModelPredictResult.Status.SUCCESS else 0
            failed += 1 if tick_res.status == ModelPredictResult.Status.FAILED else 0
            timed_out += 1 if tick_res.status == ModelPredictResult.Status.TIMEOUT else 0

        self.logger.info(f"Tick finished with {success} success, {failed} failed and {timed_out} timed out")

        return model_responses

    async def _update_game_models(self, model_responses):
        new_model_joining = {}
        model_changed_deployment = {}
        for model_runner, _ in model_responses.items():
            model_id = model_runner.model_id
            if model_id in self.game_models:
                game_model = self.game_models[model_id]
                if game_model.deployment_changed(model_runner):
                    model_changed_deployment[game_model.crunch_identifier] = model_runner
                game_model.update_runner_info(model_runner)
            else:
                game_model = Model.create(model_runner)
                self.game_models[model_id] = game_model

                self.logger.info(f"new model {game_model.player.name}/{game_model.name} joined")
                new_model_joining[game_model.crunch_identifier] = model_runner

            self.model_repository.save(game_model)

        return new_model_joining, model_changed_deployment

    def _update_prices(self):
        prices_updated = {}
        now = datetime.now(timezone.utc)
        for asset in self.asset_codes:
            last_price = self.prices_cache.get_last_price(asset)
            if last_price is not None:
                last_ts = datetime.fromtimestamp(last_price[0] + 1, tz=timezone.utc)
                new_prices = self.prices_repository.fetch_historical_prices(asset, last_ts, now, self.PRICE_RESOLUTION)
                self.prices_cache.add_prices(asset, new_prices)
                prices_updated[asset] = new_prices

        if logger.isEnabledFor(logging.DEBUG):
            for asset, prices in prices_updated.items():
                for ts, price in prices:
                    self.logger.debug(f"Price updated for {asset} at {datetime.fromtimestamp(ts)}: {price:.2f}")

        return prices_updated

    async def _predict(self, asset_code: str, horizon: int, step: int):
        self.logger.info(f"Predicting [{asset_code}] for {horizon}s and {step}s")
        now = datetime.now(timezone.utc)

        asset_code_arg = Argument(position=1, data=Variant(type=VariantType.STRING, value=encode_data(VariantType.STRING, asset_code)))
        asset_horizon_arg = Argument(position=2, data=Variant(type=VariantType.INT, value=encode_data(VariantType.INT, horizon)))
        asset_step_arg = Argument(position=3, data=Variant(type=VariantType.INT, value=encode_data(VariantType.INT, step)))

        args = ([asset_code_arg, asset_horizon_arg, asset_step_arg], [])
        call_responses = await self.model_concurrent_runner.call('predict', args)

        predictions = {}
        for model_run, prediction_res in call_responses.items():
            model_id = model_run.model_id
            if model_id not in self.game_models:
                self.logger.debug(f"Model {model_run.model_id}, {model_run.model_name} joined the game after the previous tick, we ignore his prediction")
                continue

            predictions[model_id] = Prediction.create(model_id, asset_code, horizon, step, prediction_res, now)
        self.logger.info(f"{len(predictions)} predictions got")

        # All model should predict, so if it's absent => we add one typed absent
        missing_count = len(self.game_models) - len(predictions)
        self.logger.info(f"{missing_count} missing predictions (models sit out)")
        for _, model in self.game_models.items():
            if model.crunch_identifier not in predictions:
                predictions[model.crunch_identifier] = Prediction.create_absent(model.crunch_identifier, asset_code, horizon, step, now)

        self.prediction_repository.save_all(predictions.values())

    def _init_model_runner(self):
        self.model_concurrent_runner = DynamicSubclassModelConcurrentRunner(
            self.MODEL_RUNNER_TIMEOUT,
            "condorgame",
            self.MODEL_RUNNER_NODE_HOST,
            self.MODEL_RUNNER_NODE_PORT,
            "condorgame.tracker.TrackerBase",
            max_consecutive_failures=100,
            max_consecutive_timeouts=100
        )

        return self.model_concurrent_runner

    def _init_prices_cache(self):
        self.prices_cache = PriceStore(30)
        dt = datetime.now(timezone.utc)
        from_date = dt - self.PRICES_HISTORY_PERIOD

        for asset in self.asset_codes:
            self.prices_cache.add_prices(asset, self.prices_repository.fetch_historical_prices(asset, from_date, dt, self.PRICE_RESOLUTION))

        if self.prices_cache.empty():
            raise Exception("No prices loaded from historical data provider")

    def _init_asset_configs(self):
        self.asset_configs = self.prediction_repository.fetch_active_configs()
        self.asset_group_schedulers = GroupScheduler.create_group_schedulers(self.asset_configs)
        self.asset_codes = PredictionConfig.get_active_assets(self.asset_configs)
