import asyncio
import math
import signal
import traceback
from datetime import datetime, timedelta, timezone
import logging

import newrelic.agent
import numpy
import numpy as np
from densitypdf import density_pdf

from condorgame_backend.entities.leaderboard import Leaderboard
from condorgame_backend.entities.model import ModelScore, Model, ModelScoreSnapshot
from condorgame_backend.entities.prediction import Prediction, PredictionScore, PredictionConfig, PredictionStatus, PredictionParams
from condorgame_backend.infrastructure.memory.prices_cache import PriceStore
from condorgame_backend.services.interfaces.leaderboard_repository import LeaderboardRepository
from condorgame_backend.services.interfaces.model_repository import ModelRepository
from condorgame_backend.services.interfaces.prediction_repository import PredictionRepository
from condorgame_backend.services.interfaces.price_repository import PriceRepository

from importlib.machinery import ModuleSpec
from typing import Optional

from condorgame_backend.utils.times import MINUTE

__spec__: Optional[ModuleSpec]

# ------------------------------------------------------------------
# CRPS configuration
#
# CRPS is computed as:
#
#     CRPS = ∫ (F(z) − 1[z ≥ x])² dz ,  z ∈ [t_min, t_max]
#
# where F(z) is the forecast CDF and x is the realized return.
#
# - `base_step` (seconds) defines the reference forecast resolution.
#   CRPS integration bounds are scaled relative to this step so that
#   scores remain comparable across different temporal resolutions.
#
# - `t[asset]` specifies the base half-width of the CRPS integration
#   range for each asset at the reference resolution. This value
#   represents a typical maximum price move to cover most of the
#   predictive mass while keeping integration finite and stable.
#
# - `num_points` is the number of discretization points used to 
#   numerically approximate the CRPS integral. Higher values improve 
#   accuracy but increase computation time.
#
# For steps larger than `base_step`, integration bounds are expanded
# by sqrt(step / base_step) to reflect increased uncertainty over
# longer time intervals.
#
# Check `crps_integral` in tracker_evaluator.py for more information
CRPS_BOUNDS = {
    "base_step": 300,
    "t": {
        "BTC": 1500,
        "SOL": 4,
        "ETH": 80,
        "XAUT": 33,

        "SPYX": 3.2,
        "NVDAX": 2.3,
        "TSLAX": 5.9,
        "AAPLX": 2.1,
        "GOOGLX": 3.4,
    },
    "num_points": 256
}
# ------------------------------------------------------------------
# NumPy 2.0 removed np.trapz → replaced by np.trapezoid
if hasattr(np, "trapezoid"):
    trapezoid = np.trapezoid
else:
    trapezoid = np.trapz


def crps_integral(density_dict, x, t_min=-4000, t_max=4000, num_points=CRPS_BOUNDS["num_points"]):
    """
    CRPS score (Integrated Quadratic Score) using:
    - single PDF evaluation per grid point
    - cumulative sum to get CDF

    CRPS quantifies the accuracy of probabilistic forecasts by measuring the squared distance 
    between the forecast CDF and the observed indicator function.
    """
    ts = np.linspace(t_min, t_max, num_points)
    dt = ts[1] - ts[0]

    # Vectorized PDF computation
    pdfs = np.array([density_pdf(density_dict, t) for t in ts], dtype=float)

    # Build CDF by cumulative integration
    cdfs = np.cumsum(pdfs) * dt
    cdfs = np.clip(cdfs, 0.0, 1.0)

    # Indicator
    indicators = (ts >= x).astype(float)

    # Integrate squared error
    integrand = (cdfs - indicators) ** 2
    return float(trapezoid(integrand, ts))


class ScoreService:
    PRICES_HISTORY_PERIOD = timedelta(days=7)  # Cache period for predictions
    PRICE_RESOLUTION = "minute"
    SLEEP_TIMEOUT = 1 * MINUTE

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
        self.stop_event = asyncio.Event()

        self._init_prices_cache()

    def _init_prices_cache(self):
        self.prices_cache = PriceStore(30)
        dt = datetime.now(timezone.utc)
        from_date = dt - self.PRICES_HISTORY_PERIOD

        for asset in self.asset_codes:
            self.prices_cache.add_prices(asset, self.prices_repository.fetch_historical_prices(asset, from_date, dt, self.PRICE_RESOLUTION))

    @newrelic.agent.background_task()
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

    def _refresh_models(self):
        self.models = self.model_repository.fetch_all()

    @newrelic.agent.background_task()
    def score_predictions(self) -> bool:
        """
        Loop over cached predictions and score them using the `density_pdf` function.
        """
        self.logger.info("Scoring predictions.")
        predictions = self.prediction_repository.fetch_ready_to_score()
        if len(predictions) == 0:
            self.logger.info("No predictions to score.")
            return False

        self._score_predictions(predictions)

        self.prediction_repository.save_all(predictions)

        return True

    def _score_predictions(self, predictions: list[Prediction]):
        grouped_predictions = {}
        for prediction in predictions:
            key = (prediction.params, prediction.performed_at)
            grouped_predictions.setdefault(key, []).append(prediction)

        for group_key, group_predictions in grouped_predictions.items():
            group_failed = 0

            # 1) compute raw scores
            raw_scores = []
            ok_predictions = []

            for prediction in group_predictions:
                score = self.score_prediction(prediction)  # lower the score is better it is
                prediction.score = score

                if score.success:
                    raw_scores.append(float(score.raw))
                    ok_predictions.append(prediction)
                else:
                    group_failed += 1

            # 2) apply 95th percentile cap + normalize
            if raw_scores:
                scores = np.asarray(raw_scores, dtype=float)

                # 95th percentile cap
                # worst_score = float(np.percentile(scores, 95))
                percentile_cap = float(np.percentile(scores, 95, method="closest_observation"))
                # take the observation before percentile_cap as the worst score
                lower = scores[scores < percentile_cap]
                if lower.size > 0:
                    worst_score = float(lower.max())
                else:
                    # all values equal OR percentile_cap is the minimum
                    worst_score = percentile_cap
                best_score = float(np.min(scores))

                # cap worst 95%
                scores_capped = np.minimum(scores, worst_score)

                # normalize by dispersion (guard against division by zero)
                denom = worst_score - best_score  # 0.2
                if denom == 0:
                    # all successful scores identical -> give them all the best normalized score
                    scores_norm = np.ones_like(scores_capped)
                else:
                    scores_norm = 1 - ((scores_capped - best_score) / denom)

                scores_norm = np.clip(scores_norm, 0.0, 1.0)

                # write normalized scores back (success predictions)
                for pred, norm_value in zip(ok_predictions, scores_norm):
                    pred.score.final = float(norm_value)
                    pred.score.success = True

                # failed predictions => assign worst normalized score
                for pred in group_predictions:
                    if not pred.score.success:
                        pred.score.final = 0.0

                self.logger.info(
                    f"Scored {len(group_predictions)} predictions in group, {group_failed} failed to score. "
                    f"Params: [{group_key[0]}], Performed_at: [{group_key[1]}], "
                    f"best_raw: {best_score}, worst_raw_p95: {worst_score}"
                )

            else:
                # no successful scores in this group -> everything becomes worst (0.0)
                for pred in group_predictions:
                    pred.score.raw = 0.0
                    pred.score.final = 0.0

                self.logger.info(
                    f"Scored {len(group_predictions)} predictions in group, {group_failed} failed to score. "
                    f"Params: [{group_key[0]}], Performed_at: [{group_key[1]}], "
                    f"no successful scores -> all normalized to 0.0"
                )

    def score_prediction(self, prediction: Prediction):
        total_score = 0.0
        # step = prediction.params.step
        ts = prediction.resolvable_at.timestamp()
        asset = prediction.params.asset

        if prediction.status != PredictionStatus.SUCCESS:
            return PredictionScore(None, False, f"Prediction failed: {prediction.status.name.lower()}")

        try:
            # Score predictions at each temporal resolution independently
            for step in prediction.params.steps:
                density_prediction = prediction.distributions[str(step)]

                # Get timestamp of the first prediction step
                ts_rolling = ts - step * (len(density_prediction) - 1)

                scores_step = []

                for i in range(len(density_prediction)):

                    current_price_data = self.prices_cache.get_closest_price(asset, ts_rolling)
                    previous_price_data = self.prices_cache.get_closest_price(asset, ts_rolling - step)

                    ts_rolling += step

                    if not current_price_data or not previous_price_data:
                        self.logger.warning(f"No price data found for {asset} at {ts} or {ts - step}. Skipping density scoring.")
                        continue

                    ts_current, price_current = current_price_data
                    ts_prev, price_prev = previous_price_data

                    if ts_current != ts_prev:
                        delta = (price_current - price_prev)

                        # Step-dependent scaling coefficient for CRPS bounds
                        K = np.sqrt(step / CRPS_BOUNDS["base_step"]) if step > CRPS_BOUNDS["base_step"] else 1

                        crps_value = crps_integral(
                            density_dict=density_prediction[i],
                            x=delta,
                            t_min=-K * CRPS_BOUNDS["t"][asset],
                            t_max=K * CRPS_BOUNDS["t"][asset],
                        )
                        scores_step.append(crps_value)

                total_score += np.sum(scores_step)

            # Normalize by asset-specific scale (keep scores comparable across asset)
            total_score = total_score / CRPS_BOUNDS["t"][asset]

        except Exception as e:
            tb = traceback.format_exc()
            self.logger.debug(f"Error during scoring: {e}\nTraceback:\n{tb}")
            return PredictionScore(None, False, "Scoring error: invalid prediction format or unsupported distribution")

        if not math.isfinite(total_score):
            return PredictionScore(None, False, "The final score is invalid => math.isfinite return False.")

        return PredictionScore(float(total_score), True, None)

    @newrelic.agent.background_task()
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

            model.update_score(PredictionParams(score.asset, score.horizon, score.steps),
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

    @newrelic.agent.background_task()
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
        while not self.stop_event.is_set():
            now = datetime.now(timezone.utc)
            # Fetch updated models to ensure the leaderboard contains new models joined since the last execution
            self._refresh_models()
            self._update_prices()

            if self.score_predictions():
                self.score_models()
                self.compute_leaderboard()

                self.prediction_repository.prune()
            try:
                end_time = datetime.now(timezone.utc)
                sleep_duration = max(self.SLEEP_TIMEOUT - (end_time - now).total_seconds(), 0)
                self.logger.debug("Sleeping for %d seconds", sleep_duration)
                await asyncio.wait_for(self.stop_event.wait(), timeout=sleep_duration)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self):
        self.stop_event.set()
