import asyncio
import math
import signal
import traceback
from datetime import datetime, timedelta, timezone
import logging

import numpy
import numpy as np
from densitypdf import density_pdf

from falcon2_backend.entities.leaderboard import Leaderboard
from falcon2_backend.entities.model import ModelScore, Model, ModelScoreSnapshot
from falcon2_backend.entities.prediction import Prediction, PredictionScore, PredictionConfig, PredictionStatus, PredictionParams
from falcon2_backend.infrastructure.memory.prices_cache import PriceStore
from falcon2_backend.services.interfaces.leaderboard_repository import LeaderboardRepository
from falcon2_backend.services.interfaces.model_repository import ModelRepository
from falcon2_backend.services.interfaces.prediction_repository import PredictionRepository
from falcon2_backend.services.interfaces.price_repository import PriceRepository

from importlib.machinery import ModuleSpec
from typing import Optional

__spec__: Optional[ModuleSpec]

MINUTE = 60


class ScoreService:
    PRICES_HISTORY_PERIOD = timedelta(days=7)  # Cache period for predictions
    PRICE_RESOLUTION = "minute"
    SLEEP_TIMEOUT = 15 * MINUTE

    def __init__(self,
                 prices_repository: PriceRepository,
                 model_repository: ModelRepository,
                 prediction_repository: PredictionRepository,
                 leaderboard_repository: LeaderboardRepository,

                 ):
        """
        Initialize the ScoreService.

        :param prediction_repository: repository for managing predictions (e.g., fetching and updating).
        :param density_pdf: callable function to compute the likelihood for scoring.
        """

        self.last_leaderboard = None
        self.prices_repository = prices_repository
        self.model_repository = model_repository
        self.prediction_repository = prediction_repository
        self.leaderboard_repository = leaderboard_repository

        self.logger = logging.getLogger(__spec__.name if __spec__ else __name__)

        self.asset_codes = PredictionConfig.get_active_assets(self.prediction_repository.fetch_active_configs())
        self.models = self.model_repository.fetch_all()

        self.stop_event = asyncio.Event()

        self._init_prices_cache()

    def _init_prices_cache(self):
        self.prices_cache = PriceStore(30)
        dt = datetime.now(timezone.utc)
        from_date = dt - self.PRICES_HISTORY_PERIOD

        for asset in self.asset_codes:
            self.prices_cache.add_prices(asset, self.prices_repository.fetch_historical_prices(asset, from_date, dt, self.PRICE_RESOLUTION))

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

        if self.logger.isEnabledFor(logging.DEBUG):
            for asset, prices in prices_updated.items():
                for ts, price in prices:
                    self.logger.debug(f"Price updated for {asset} at {datetime.fromtimestamp(ts)}: {price:.2f}")

        return prices_updated

    def score_predictions(self) -> bool:
        """
        Loop over cached predictions and score them using the `density_pdf` function.
        """
        self.logger.info("Scoring predictions.")
        scored_count = 0
        score_failed_count = 0
        predictions = self.prediction_repository.fetch_ready_to_score()
        if len(predictions) == 0:
            self.logger.info("No predictions to score.")
            return False

        min_score = 0.0
        for prediction in predictions:
            score = self.score_prediction(prediction)
            prediction.score = score

            if score.success:
                min_score = min(min_score, score.value)
            else:
                score_failed_count += 1

            scored_count += 1

        self.logger.info(f"Scored {scored_count} predictions, {score_failed_count} failed to score. Minimum score: {min_score}")

        # if the prediction failed to score => we assign the minimum score
        for prediction in predictions:
            if not prediction.score.success:
                prediction.score.value = min_score

        self.prediction_repository.save_all(predictions)

        self.logger.info(f"Scored {scored_count} predictions")

        return True

    def score_prediction(self, prediction: Prediction):
        densities = []
        step = prediction.params.step
        ts = prediction.resolvable_at.timestamp()
        asset = prediction.params.asset

        if prediction.status != PredictionStatus.SUCCESS:
            return PredictionScore(None, False, f"The prediction not succeed {prediction.status}")

        if len(prediction.distributions) != prediction.params.horizon / step:
            return PredictionScore(None, False, "The prediction does not have the correct number of steps")
        try:
            for density_prediction in prediction.distributions[::-1]:
                current_price_data = self.prices_cache.get_closest_price(asset, ts)
                previous_price_data = self.prices_cache.get_closest_price(asset, ts - step)

                if not current_price_data or not previous_price_data:
                    self.logger.warning(f"No price data found for {asset} at {ts} or {ts - step}. Skipping density scoring.")
                    continue

                ts_current, price_current = current_price_data
                ts_prev, price_prev = previous_price_data

                if ts_current != ts_prev:
                    delta_price = np.log(price_current) - np.log(price_prev)
                    pdf_value = density_pdf(density_dict=density_prediction, x=delta_price)
                    densities.append(pdf_value)

                ts -= step
        except Exception as e:
            tb = traceback.format_exc()
            self.logger.debug(f"Error during scoring: {e}\nTraceback:\n{tb}")
            return PredictionScore(None, False, f"Error during scoring: {e}\nTraceback:\n{tb}")

        score = numpy.mean(densities)

        if not math.isfinite(score):
            return PredictionScore(None, False, "The final score is invalid => math.isfinite return True.")

        return PredictionScore(float(score), True, None)

    def score_models(self):

        # for now, use SQL to optimize the model score compute
        scores = self.prediction_repository.fetch_all_windowed_scores()
        if not scores:
            return

        for score in scores:
            model = self.models[score.model_id]
            if not model:
                # think maybe to fetch all every call? or update the dictionary from predict_service?
                self.models[score.model_id] = self.model_repository.fetch(score.model_id)
                model = self.models[score.model_id]

                self.logger.error(f"Model {score.model_id} not found in the model repository")

            model.update_score(PredictionParams(score.asset, score.horizon, score.step),
                               ModelScore(score.recent_mean, score.steady_mean, score.anchor_mean))

        models = self.models.values()
        if not models:
            return

        dt = datetime.now(timezone.utc)
        for model in models:
            model.calc_overall_score()

        self.model_repository.save_all(models)

        self.model_repository.snapshot_model_scores([
            ModelScoreSnapshot.create(model, dt)
            for model in models
            if model.has_score()  # if the model still not have any score, no need to snapshot
        ])
        self.model_repository.prune_snapshots()

    def compute_leaderboard(self):
        leaderboard = Leaderboard.create(self.models.values())

        top1 = self.models[leaderboard.entries[0].model_id].qualified_name() if leaderboard.entries else None
        self.logger.info(f"Leaderboard created with {len(leaderboard.entries)} positions. TOP 1: {top1}")

        self.leaderboard_repository.save(leaderboard)
        self.last_leaderboard = leaderboard

    async def run(self):
        """
        Main loop for scoring predictions.
        """
        loop = asyncio.get_event_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown()))

        self.logger.info("run")
        try:

            await self._run()

        except asyncio.CancelledError:
            self.logger.info("CancelledError")
        except Exception as e:
            self.logger.exception(e)
        finally:
            await self.shutdown()
            self.logger.info("run finished")

        self.logger.info("ScoreService started.")

        self.logger.info("ScoreService completed.")

    async def _run(self):
        force_scoring = True
        while not self.stop_event.is_set():
            self._update_prices()

            if self.score_predictions() or force_scoring:
                self.score_models()
                self.compute_leaderboard()

                self.prediction_repository.prune()
            try:
                self.logger.debug("Sleeping for %d seconds", self.SLEEP_TIMEOUT)
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.SLEEP_TIMEOUT)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self):
        self.stop_event.set()
