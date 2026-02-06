import asyncio
import math
import signal
import traceback
from datetime import datetime, timedelta, timezone, date
import logging
from time import sleep
import requests
from requests.adapters import HTTPAdapter, Retry
from tqdm import tqdm

import numpy
import numpy as np
import pandas as pd

from condorgame_backend.entities.daily_synth_leaderboard import DailySynthLeaderboard
from condorgame_backend.entities.model import ModelScore, Model, ModelScoreSnapshot
from condorgame_backend.entities.prediction import Prediction, PredictionScore, PredictionConfig, PredictionStatus, PredictionParams
from condorgame_backend.infrastructure.memory.prices_cache import PriceStore
from condorgame_backend.services.interfaces.daily_synth_leaderboard_repository import SynthLeaderboardRepository
from condorgame_backend.services.interfaces.model_repository import ModelRepository
from condorgame_backend.services.interfaces.prediction_repository import PredictionRepository
from condorgame_backend.services.interfaces.price_repository import PriceRepository

from importlib.machinery import ModuleSpec
from typing import Optional, Any, Dict, List

from condorgame_backend.utils.times import MINUTE

__spec__: Optional[ModuleSpec]

ASSETS = ["BTC", "SOL", "ETH", "XAUT", "SPYX", "NVDAX", "TSLAX", "AAPLX", "GOOGLX"] # Supported assets: "BTC", "SOL", "ETH", "XAUT", "SPYX", "NVDAX", "TSLAX", "AAPLX", "GOOGLX"
LIST_PARAMS_HORIZON = [(86400, 300), (3600, 60)]


from properscoring import crps_ensemble

def get_interval_steps(interval_seconds: int, time_increment: int) -> int:
    return int(interval_seconds / time_increment)

def score_summary(score_details):
    filtered = score_details[score_details["block"] == "TOTAL"]
    filtered = filtered[["interval", "crps"]]

    return filtered.to_string(index=False)


def label_observed_blocks(arr: np.ndarray) -> np.ndarray:
    """
    groups consecutive NON-MISSING values into blocks.
    Missing values = gaps = block -1.
    """
    not_nan = ~np.isnan(arr)
    block_start = not_nan & np.concatenate(([True], ~not_nan[:-1]))
    group_numbers = np.cumsum(block_start) - 1
    return np.where(not_nan, group_numbers, -1)


def calculate_price_changes_over_intervals(
    price_paths: np.ndarray,
    interval_steps: int,
    absolute_price=False,
    is_gap=False,
) -> np.ndarray:
    """
    Computes the interval values:
      - returns (ΔP / P * 10000)
      - absolute prices (dropping first point)
      - gap handling
    """
    interval_prices = price_paths[:, ::interval_steps]

    if is_gap:
        interval_prices = interval_prices[:1]   # first point only

    if absolute_price:
        # For absolute prices, drop first point
        return interval_prices[:, 1:]

    # Relative returns
    return (np.diff(interval_prices, axis=1) / interval_prices[:, :-1]) * 10000


def crps_ensemble_score(
    real_price_path: np.ndarray,
    simulation_runs: np.ndarray,
    time_increment: int,
    scoring_intervals: dict,
):
    detailed = []
    dict_int = {}
    total_score = 0.0

    for name, interval_seconds in scoring_intervals.items():

        interval_steps = get_interval_steps(interval_seconds, time_increment)
        if interval_steps < 1:
            continue

        absolute_price = name.endswith("_abs")
        is_gap = name.endswith("_gap")

        # Fix intervals when only one point exists
        if absolute_price:
            while (
                real_price_path[::interval_steps].shape[0] == 1
                and interval_steps > 1
            ):
                interval_steps -= 1

        # --- Compute price changes for this interval ---
        simulated_changes = calculate_price_changes_over_intervals(
            simulation_runs,
            interval_steps,
            absolute_price,
            is_gap,
        )
        real_changes = calculate_price_changes_over_intervals(
            real_price_path.reshape(1, -1),
            interval_steps,
            absolute_price,
            is_gap,
        )

        # Identify valid blocks (skipping gaps)
        data_blocks = label_observed_blocks(real_changes[0])
        if len(data_blocks) == 0:
            continue

        interval_total = 0.0

        # Compute CRPS block-by-block
        for block_id in np.unique(data_blocks):
            if block_id == -1:
                continue

            mask = data_blocks == block_id

            sim_block = simulated_changes[:, mask]
            obs_block = real_changes[:, mask][0]

            for t in range(sim_block.shape[1]):
                obs = obs_block[t]
                forecasts = sim_block[:, t]
                crps_val = crps_ensemble(obs, forecasts)

                # Scaling for absolute prices
                if absolute_price:
                    crps_val = (crps_val / real_price_path[-1]) * 10000

                interval_total += crps_val

                detailed.append({
                    "interval": name,
                    "block": int(block_id),
                    "crps": float(crps_val),
                })

        total_score += interval_total

        detailed.append({
            "interval": name,
            "block": "TOTAL",
            "crps": float(interval_total),
        })
        dict_int[name] = float(interval_total)

    detailed.append({
        "interval": "OVERALL",
        "block": "TOTAL",
        "crps": float(total_score),
    })

    return total_score, detailed, dict_int

scoring_intervals={
        300: {
        "5min": 300,  # 5 minutes
        "30min": 1800,  # 30 minutes
        "3hour": 10800,  # 3 hours
        "24hour_abs": 86400,  # 24 hours
        },
        60: {
        "1min": 60,
        "2min": 120,
        "5min": 300,
        "15min": 900,
        "30min": 1800,
        "60min_abs": 3600,
        "0_5min_gaps": 300,
        "0_10min_gaps": 600,
        "0_15min_gaps": 900,
        "0_20min_gaps": 1200,
        "0_25min_gaps": 1500,
        "0_30min_gaps": 1800,
        "0_35min_gaps": 2100,
        "0_40min_gaps": 2400,
        "0_45min_gaps": 2700,
        "0_50min_gaps": 3000,
        "0_55min_gaps": 3300,
        "0_60min_gaps": 3600,
        }
    }

import bisect
def rank(value, lst):
    return bisect.bisect_left(sorted(lst), value) + 1


def transform_data(
    data_, start_time_int: int, time_increment: int, time_length: int
) -> list:
    
    data = {}
    data["t"] = [t[0] for t in data_]
    data["c"] = [t[1] for t in data_]

    if data is None or len(data) == 0 or len(data["t"]) == 0:
        return []

    time_end_int = start_time_int + time_length
    timestamps = [
        t
        for t in range(
            start_time_int, time_end_int + time_increment, time_increment
        )
    ]

    if len(timestamps) != int(time_length / time_increment) + 1:
        # Note: this part of code should never be activated; just included for precaution
        if len(timestamps) == int(time_length / time_increment) + 2:
            if data["t"][-1] < timestamps[1]:
                timestamps = timestamps[:-1]
            elif data["t"][0] > timestamps[0]:
                timestamps = timestamps[1:]
        else:
            return []

    close_prices_dict = {t: c for t, c in zip(data["t"], data["c"])}
    transformed_data = [np.nan for _ in range(len(timestamps))]

    for idx, t in enumerate(timestamps):
        if t in close_prices_dict:
            transformed_data[idx] = close_prices_dict[t]

    return np.array(transformed_data)


class DailySynthScoreService:
    PRICES_HISTORY_PERIOD = timedelta(days=30)  # Cache period for predictions
    PRICE_RESOLUTION = "minute"
    SLEEP_TIMEOUT = 60 * MINUTE * 3 # Run every 

    def __init__(self,
                 prices_repository: PriceRepository,
                 model_repository: ModelRepository,
                 prediction_repository: PredictionRepository,
                 daily_synth_leaderboard_repo: SynthLeaderboardRepository,

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
        self.daily_synth_leaderboard_repo = daily_synth_leaderboard_repo

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
        self.models = self.model_repository.fetch_all(apply_row_to_domain=False)

    def score_predictions(self, day: date) -> pd.DataFrame:

        print(f"Scoring predictions for day {day}.")

        all_leaderboard = []

        print("\n*****************************************************************")
        print("*****************************************************************")
        print("DAY:", day)
        print("*****************************************************************")

        for time_length, time_increment in LIST_PARAMS_HORIZON:

            print("#################################################################")
            print("#################################################################")
            print("time_length:", time_length, day)
            print("#################################################################")

            for asset in ASSETS:

                if time_length == 3600 and asset not in ["BTC", "SOL", "ETH", "XAUT"]:
                    continue

                print("\n#################################################################")
                print("ASSET:", asset, time_length, day)
                print("#################################################################")

                print("Tracker models: get all tracker predictions from a daily prediction round")
                predictions = self.prediction_repository.fetch_predictions_one_day(
                                    day=day, asset=asset, horizon=time_length)
                
                if len(predictions) == 0:
                    print(f"No predictions to score for day {day}, horizon {time_length}, asset {asset}.")
                    continue
                
                prediction_round = pd.DataFrame(predictions)

                # Load models table to get player names and model names
                models_df = pd.DataFrame(self.models)

                # Merge on model_id → crunch_identifier
                prediction_round = prediction_round.merge(
                    models_df[["crunch_identifier", "player_name", "name"]],
                    left_on="model_id",
                    right_on="crunch_identifier",
                    how="left"
                )

                prediction_round = prediction_round.drop(columns=["crunch_identifier"])

                df_prediction_round = prediction_round[["model_id", "player_name", "name", "asset", "horizon", "score_raw_value", "distributions", "resolvable_at", "status"]]
                df_prediction_round.loc[:,"model_id"] = df_prediction_round["model_id"].apply(lambda x: "crunch_"+x)
                df_prediction_round.columns = ["miner_uid", "player_name", "model", "asset", "time_length", "crunch_score", "prediction", "scored_time", "status"]
                df_prediction_round["scored_time"] = df_prediction_round["scored_time"].apply(lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ"))
                
                leaderboard_prompt_score = self._score_predictions(df_prediction_round, day, asset, time_length, time_increment)

                if leaderboard_prompt_score is not None:
                    all_leaderboard.append(leaderboard_prompt_score)
        
        if len(all_leaderboard) == 0:
            return None
        
        leaderboard_prompt_score_final = self.compute_global_daily_leaderboard(all_leaderboard, day, time_length)
        all_leaderboard_final = pd.concat(all_leaderboard + [leaderboard_prompt_score_final]).reset_index(drop=True)
        
        return all_leaderboard_final

    def _score_predictions(self, df_prediction_round: pd.DataFrame, day: date, asset: str, time_length: int, time_increment: int):
        df_all = df_prediction_round[(df_prediction_round.asset == asset) & (df_prediction_round.time_length == time_length)].copy()
        print(df_all)

        # get models present at each prediction round of the day
        trackers_present_all_time = list(df_all.miner_uid.value_counts()[(df_all.miner_uid.value_counts() == max(df_all.miner_uid.value_counts()))].index)
        df_all = df_all[df_all.miner_uid.isin(trackers_present_all_time)]

        #############
        # SYNTH score: Query SYNTH API: get all miner scores from a prediction round
        #############
        print(f"Query SYNTH API: get all miner scores for day {day} time_length {time_length}")
        from_date = df_all.scored_time.min()
        from_date = datetime.fromisoformat(from_date.replace("Z", "+00:00")).astimezone(timezone.utc) #- timedelta(hours=1)

        to_date = df_all.scored_time.max()
        to_date = datetime.fromisoformat(to_date.replace("Z", "+00:00")).astimezone(timezone.utc) + timedelta(hours=1)

        synth_data_json = self._fetch_historical(base_url="mainnet", 
                            start_dt=from_date, 
                            end_dt=to_date,
                            asset=asset if asset != "XAUT" else "XAU",
                            miner_uid=None,
                            time_increment=time_increment,
                            time_length=time_length,
                            )

        df_synth_data = pd.DataFrame(synth_data_json)

        if len(df_synth_data) == 0:
            return None

        df_synth_data["miner_uid"] = df_synth_data["miner_uid"].apply(str)
        validators_not_miner = ['34' , '1' ,'17', '38' ,'151', '8', '128', '53' ,'130' ,'162', '248' ,'0' ,'221']
        df_synth_data = df_synth_data[~df_synth_data["miner_uid"].isin(validators_not_miner)]

        if asset == "XAUT":
            # replace "XAU" by "XAUT"
            df_synth_data["asset"] = asset

        df_synth_data = df_synth_data[df_synth_data.scored_time >= from_date.strftime("%Y-%m-%dT%H:%M:%SZ")]
        df_synth_data = df_synth_data[df_synth_data.scored_time <= to_date.strftime("%Y-%m-%dT%H:%M:%SZ")]

        print("Synth scores")
        print(df_synth_data)

        df_synth_data["player_name"] = df_synth_data["miner_uid"]
        df_synth_data["model"] = df_synth_data["miner_uid"]

        if len(df_synth_data) == 0:
            return None
        
        #############
        # Merging: for trackers, synchronize scored_time_crunch and scored_time from synth
        #############

        left_data = df_all.copy()
        left_data = left_data.sort_values("scored_time")
        left_data = left_data.rename(columns={"scored_time": "scored_time_crunch"})

        right_data = df_synth_data[["scored_time"]].drop_duplicates().copy()
        right_data = right_data.sort_values("scored_time")

        left_data.scored_time_crunch = left_data.scored_time_crunch.apply(lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc))
        right_data.scored_time = right_data.scored_time.apply(lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc))

        df_merge_tracker = pd.merge_asof(left_data, right_data, left_on="scored_time_crunch", right_on="scored_time", direction="forward")
        df_merge_tracker = df_merge_tracker[~df_merge_tracker.scored_time.isna()]
        df_merge_tracker = df_merge_tracker.drop_duplicates(subset=["miner_uid", "asset", "time_length", "scored_time"], keep="last")
        print("Merging: for trackers, synchronize scored_time_crunch and scored_time from synth")
        print(df_merge_tracker)

        #############
        # Compute synth crps score for trackers: Simulate paths and compute crps ensemble score
        #############
        print("Compute synth crps score for trackers: Simulate paths and compute crps ensemble score")
        cache_past_true_prices = {}
        list_all_crps = []
        for i, row in tqdm(df_merge_tracker.iterrows(), total=len(df_merge_tracker)):
            total_score = self.score_prediction(row, df_synth_data, cache_past_true_prices, time_increment)
            list_all_crps.append(total_score)

        df_merge_tracker["crps"] = list_all_crps

        print("crps score for trackers:")
        print(df_merge_tracker)

        #############
        # Merging: synth_data and my trackers
        #############
        print("Merging: synth_data and trackers")

        df_synth_data_ = df_synth_data.copy()
        df_synth_data_.scored_time = df_synth_data_.scored_time.apply(lambda x: datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc))
        df_synth_data_ = df_synth_data_[df_synth_data_.scored_time.isin(list(df_merge_tracker.scored_time.unique()))]
        left_data = pd.concat([df_synth_data_, df_merge_tracker]).copy()
        left_data = left_data.sort_values("scored_time")
        left_data_copy = left_data.copy()

        # remove prediction round where less than 150 miners
        mask = (
            left_data
                .groupby("scored_time")
                .transform("size") < 150
        )
        left_data_under_150 = list(left_data[mask]["scored_time"])
        left_data = left_data[~left_data.scored_time.isin(left_data_under_150)]

        # remove prediction round where lot of same crps: would mean there was an error on synth validation side
        scored_time_with_dominant_crps = list(
            left_data
                .groupby("scored_time")["crps"]
                .apply(lambda s: s.value_counts().iloc[0] > 50)
                .loc[lambda s: s]
                .index
        )
        left_data = left_data[~left_data.scored_time.isin(scored_time_with_dominant_crps)]

        #########################
        # fill -1 prompt_score
        grp_cols = ["asset", "time_length", "scored_time"]
        min_crps = (
            left_data
                .assign(
                    crps_pos=lambda df: df["crps"].where(
                        (df["crps"] > 0) & (df["prompt_score"] >= 0)
                    )
                )
                .groupby(grp_cols)["crps_pos"]
                .transform("min")
        )
        max_prompt_score = (
            left_data
                .groupby(grp_cols)["prompt_score"]
                .transform("max")
        )

        left_data["prompt_score"] = left_data["prompt_score"].fillna(-1)
        mask = left_data["prompt_score"] == -1
        left_data.loc[mask, "prompt_score"] = (
            (left_data.loc[mask, "crps"] - min_crps[mask])
                .clip(upper=max_prompt_score[mask])
        )

        #########################
        # fill -1 crps by max crps
        left_data["crps"] = left_data.groupby("scored_time")["crps"].transform(
            lambda x: (x.mask(x == -1, x.max()))
        )

        # In case we removed all prediction round
        if len(left_data) == 0:
            left_data = {
                "miner_uid": list(left_data_copy.miner_uid.unique())
            }
            left_data["prompt_score"] = [-1 for i in range(len(left_data["miner_uid"]))]
            left_data = pd.DataFrame(left_data)
        #########################

        # Crunch models
        crunch_uids = set(df_all.miner_uid.unique())

        print("ratio get max_prompt_score")
        left_data["equal_max_cap"] = left_data.groupby("scored_time")["prompt_score"].transform("max") == left_data["prompt_score"]
        print(left_data[left_data.miner_uid.isin(list(crunch_uids))].groupby(["miner_uid", "player_name", "model"])[["equal_max_cap"]].mean())

        #############
        # Leaderboard prompt_score
        #############
        print(f"Leaderboard prompt_score: {asset} time_length: {time_length} day: {day}")

        # Compute mean prompt_score per miner
        leaderboard_prompt_score = (
            left_data
                .groupby(["miner_uid", "player_name", "model"], as_index=False)
                .agg(
                    mean_prompt_score=("prompt_score", "mean"),
                    mean_crps_score=("crps", "mean"),
                    mean_crunch_score=("crunch_score", "mean"),
                    n_scores=("prompt_score", "count"),
                    ratio_max_cap=("equal_max_cap", "mean"),
                )
        )

        # RANK PROMPT SCORE
        # Compute rank ignoring crunch miners
        mask = ~leaderboard_prompt_score["miner_uid"].isin(crunch_uids)
        leaderboard_prompt_score.loc[mask, "rank"] = (
            leaderboard_prompt_score.loc[mask, "mean_prompt_score"]
                .rank(method="max", ascending=True)
                .astype(int)
        )

        # Assign phantom ranks to crunch miners one by one
        for uid in crunch_uids:
            if uid in leaderboard_prompt_score["miner_uid"].values:
                # Get the score of this crunch miner
                score = leaderboard_prompt_score.loc[leaderboard_prompt_score["miner_uid"] == uid, "mean_prompt_score"].iloc[0]
                # Count how many miners have smaller scores in the leaderboard
                phantom_rank = (leaderboard_prompt_score.loc[mask, "mean_prompt_score"] <= score).sum() + 1
                # Assign the phantom rank
                leaderboard_prompt_score.loc[leaderboard_prompt_score["miner_uid"] == uid, "rank"] = phantom_rank

        # RANK CRPS SCORE
        # Compute rank ignoring crunch miners
        mask = ~leaderboard_prompt_score["miner_uid"].isin(crunch_uids)
        leaderboard_prompt_score.loc[mask, "rank_crps"] = (
            leaderboard_prompt_score.loc[mask, "mean_crps_score"]
                .rank(method="max", ascending=True)
                .astype(int)
        )

        # Assign phantom ranks to crunch miners one by one
        for uid in crunch_uids:
            if uid in leaderboard_prompt_score["miner_uid"].values:
                # Get the score of this crunch miner
                score = leaderboard_prompt_score.loc[leaderboard_prompt_score["miner_uid"] == uid, "mean_crps_score"].iloc[0]
                # Count how many miners have smaller scores in the leaderboard
                phantom_rank = (leaderboard_prompt_score.loc[mask, "mean_crps_score"] <= score).sum() + 1
                # Assign the phantom rank
                leaderboard_prompt_score.loc[leaderboard_prompt_score["miner_uid"] == uid, "rank_crps"] = phantom_rank

        leaderboard_prompt_score = leaderboard_prompt_score.sort_values(
            ["rank", "mean_prompt_score"]
        )
        
        leaderboard_prompt_score["rank"] = leaderboard_prompt_score["rank"].apply(int)
        leaderboard_prompt_score["rank_crps"] = leaderboard_prompt_score["rank_crps"].apply(int)
        leaderboard_prompt_score["asset"] = asset
        leaderboard_prompt_score["time_length"] = time_length
        leaderboard_prompt_score["day"] = day
        leaderboard_prompt_score["crunch_model"] = leaderboard_prompt_score["miner_uid"].isin(crunch_uids)
        leaderboard_prompt_score["leaderboard_compute_at"] = datetime.now(timezone.utc)

        max_n_scores = max(leaderboard_prompt_score.n_scores)
        leaderboard_prompt_score = leaderboard_prompt_score[leaderboard_prompt_score.n_scores==max_n_scores]

        cols = ["miner_uid", "player_name", "model", "rank", "mean_prompt_score", "rank_crps", "mean_crps_score", "mean_crunch_score", "ratio_max_cap", "asset"]
        print(leaderboard_prompt_score[cols])
        print(leaderboard_prompt_score[leaderboard_prompt_score.crunch_model][cols])
        print("correlation synth/crunch score:", 
                leaderboard_prompt_score[(leaderboard_prompt_score.crunch_model) & (leaderboard_prompt_score.mean_crunch_score > 0)].iloc[:20][["mean_crps_score", "mean_crunch_score"]].corr().iloc[0, 1])

        return leaderboard_prompt_score

    def score_prediction(self, row, df_synth_data: pd.DataFrame, cache_past_true_prices: dict, time_increment: int):

        asset = row.asset
        time_length = row.time_length
        prediction = row.prediction
        resolvable_at = row.scored_time
        model_id = row.miner_uid
        success_prediction = row.status == "SUCCESS"

        ### Get synth scoring for this specific scored_time
        subset_synth = df_synth_data[df_synth_data.scored_time == resolvable_at.strftime("%Y-%m-%dT%H:%M:%SZ")]
        subset_synth = subset_synth[subset_synth.crps > 0]
        # if error give max crps from synth
        subset_synth_max_crps = max(subset_synth.crps)

        if not success_prediction:
            total_score = subset_synth_max_crps
            self.logger.info(f"ABSENT Model_ID {model_id}: {total_score} | rank:{rank(total_score, list(subset_synth["crps"]))}/{len(subset_synth)} | prompt_score: {total_score - min(subset_synth["crps"])}")
            return total_score
        
        try:
            #####################
            # Get true prices
            if resolvable_at in cache_past_true_prices:
                real_price_path = cache_past_true_prices[resolvable_at]
            else:

                past_prices = self.prices_cache.get_price_history(
                            asset=asset,
                            from_=resolvable_at - timedelta(seconds=time_length),
                            to=resolvable_at + timedelta(seconds=1),
                        )

                real_price_path = transform_data(
                    past_prices, start_time_int=int(resolvable_at.timestamp()) - time_length, time_increment=time_increment, time_length=time_length
                )
                
                cache_past_true_prices[resolvable_at] = real_price_path
            #####################

            #####################
            # Simulate paths from distribution prediction
            dict_paths = {}
            for resolution in prediction.keys():

                preds_resolution = prediction[resolution]

                simulations = simulate_paths(
                        preds_resolution,
                        start_point=0.0,
                        num_paths=1000,
                        step_minutes=None,
                        start_time=None,
                        mode="point"
                    )
                paths = simulations["paths"]
                dict_paths[resolution] = paths[:, 1:]

            resolution_config = {str(resolution): int(resolution) for resolution in dict_paths.keys()}
            pred_paths = combine_multiscale_simulations(dict_paths, resolution_config)

            # Add start price to simulated final paths
            pred_paths = real_price_path[0] + pred_paths
            #####################

            #####################
            # Compute CRPS
            total_score, detailed, dict_int = crps_ensemble_score(
                        real_price_path,
                        pred_paths,
                        time_increment,
                        scoring_intervals[time_increment]
                    )
            total_score = float(total_score)
            
        except Exception as e:
            self.logger.debug(f"Error compute synth crps score for Model_ID {model_id}: {e}")
            total_score = subset_synth_max_crps
        
        self.logger.info(f"Model_ID {model_id}: {total_score} | rank:{rank(total_score, list(subset_synth["crps"]))}/{len(subset_synth)} | prompt_score: {total_score - min(subset_synth["crps"])}")

        return total_score
    
    def _fetch_historical(self, base_url: str, start_dt: str, end_dt: str,
                     asset: Optional[str], miner_uid: Optional[int],
                     time_increment: Optional[int], time_length: Optional[int]) -> List[Dict[str, Any]]:
        """
        Fetch historical scores between start_dt and end_dt, splitting into 7-day chunks if necessary.
        """
        url = f"https://api.synthdata.co/validation/scores/historical"

        def iso_to_dt(s: str) -> datetime:
            s = s.replace("Z", "+00:00")
            return datetime.fromisoformat(s).astimezone(timezone.utc)

        def dt_to_iso(dt: datetime) -> str:
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # --- HTTP helpers
        def http_session():
            s = requests.Session()
            r = Retry(total=5, backoff_factor=0.4,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["GET"])
            s.mount("https://", HTTPAdapter(max_retries=r))
            return s

        print(start_dt)
        all_data: List[Dict[str, Any]] = []

        MAX_DAYS_PER_CALL = 6
        with http_session() as s:
            while start_dt < end_dt:
                chunk_end = min(start_dt + timedelta(days=MAX_DAYS_PER_CALL), end_dt)
                params = {"from": dt_to_iso(start_dt), "to": dt_to_iso(chunk_end)}
                if asset:
                    params["asset"] = asset
                if miner_uid is not None:
                    params["miner_uid"] = miner_uid
                if time_increment is not None:
                    params["time_increment"] = time_increment
                if time_length is not None:
                    params["time_length"] = time_length

                print(f"Fetching {params['from']} → {params['to']} ...")
                r = s.get(url, params=params, timeout=60)
                if r.status_code == 404:
                    print(f"No data for {params['from']} → {params['to']}, skipping.")
                    start_dt = chunk_end
                    sleep(1)
                    continue
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, list):
                    raise ValueError(f"Unexpected response format for chunk {params}")
                all_data.extend(data)

                start_dt = chunk_end  # move to next window
                sleep(1)

        return all_data

    def compute_global_daily_leaderboard(self, all_leaderboard: pd.DataFrame, day: date, time_length: int):
        #############
        # Leaderboard prompt_score final
        #############
        print("#################################################################")
        print("#################################################################")
        print(f"Leaderboard prompt_score FINAL time_length:", time_length, "day", day)
        print("#################################################################")

        def apply_per_asset_coefficients(df, col):
            asset_coefficients = {
                "BTC": 1.0,
                "ETH": 0.6715516528608204,
                "XAUT": 2.262003561659039,
                "SOL": 0.5883682889710361,
                "SPYX": 2.9914378891824693,
                "NVDAX": 1.3885444209082594,
                "TSLAX": 1.420016421725336,
                "AAPLX": 1.864976360560554,
                "GOOGLX": 1.4310534797250312,
            }

            coefs = df["asset"].map(asset_coefficients).fillna(1.0)

            weighted = df[col] * coefs
            norm = (coefs).sum()

            return weighted / norm

        final_leaderbaord = pd.concat(all_leaderboard).reset_index(drop=True)
        final_leaderbaord["mean_prompt_score"] = (
            final_leaderbaord
                .groupby("miner_uid", group_keys=False)
                .apply(apply_per_asset_coefficients, col="mean_prompt_score", include_groups=False)
        )

        final_leaderbaord["mean_crps_score"] = (
            final_leaderbaord
                .groupby("miner_uid", group_keys=False)
                .apply(apply_per_asset_coefficients, col="mean_crps_score", include_groups=False)
        )

        final_leaderbaord["mean_crunch_score"] = (
            final_leaderbaord
                .groupby("miner_uid", group_keys=False)
                .apply(apply_per_asset_coefficients, col="mean_crunch_score", include_groups=False)
        )

        leaderboard_prompt_score_final = (
                final_leaderbaord
                    .groupby(["miner_uid", "player_name", "model"], as_index=False)
                    .agg(
                        mean_prompt_score=("mean_prompt_score", "sum"),
                        mean_crps_score=("mean_crps_score", "sum"),
                        mean_crunch_score=("mean_crunch_score", "sum"),
                        n_scores=("n_scores", "mean"),
                        ratio_max_cap=("ratio_max_cap", "mean"),
                    )
            )

        crunch_uids = list(final_leaderbaord[final_leaderbaord.crunch_model].miner_uid.unique())

        # RANK PROMPT SCORE
        # Compute rank ignoring crunch miners
        mask = ~leaderboard_prompt_score_final["miner_uid"].isin(crunch_uids)
        leaderboard_prompt_score_final.loc[mask, "rank"] = (
            leaderboard_prompt_score_final.loc[mask, "mean_prompt_score"]
                .rank(method="max", ascending=True)
                .astype(int)
        )

        # Assign phantom ranks to crunch miners one by one
        for uid in crunch_uids:
            if uid in leaderboard_prompt_score_final["miner_uid"].values:
                # Get the score of this crunch miner
                score = leaderboard_prompt_score_final.loc[leaderboard_prompt_score_final["miner_uid"] == uid, "mean_prompt_score"].iloc[0]
                # Count how many miners have smaller scores in the leaderboard
                phantom_rank = (leaderboard_prompt_score_final.loc[mask, "mean_prompt_score"] <= score).sum() + 1
                # Assign the phantom rank
                leaderboard_prompt_score_final.loc[leaderboard_prompt_score_final["miner_uid"] == uid, "rank"] = phantom_rank

        # RANK CRPS SCORE
        # Compute rank ignoring crunch miners
        mask = ~leaderboard_prompt_score_final["miner_uid"].isin(crunch_uids)
        leaderboard_prompt_score_final.loc[mask, "rank_crps"] = (
            leaderboard_prompt_score_final.loc[mask, "mean_crps_score"]
                .rank(method="max", ascending=True)
                .astype(int)
        )

        # Assign phantom ranks to crunch miners one by one
        for uid in crunch_uids:
            if uid in leaderboard_prompt_score_final["miner_uid"].values:
                # Get the score of this crunch miner
                score = leaderboard_prompt_score_final.loc[leaderboard_prompt_score_final["miner_uid"] == uid, "mean_crps_score"].iloc[0]
                # Count how many miners have smaller scores in the leaderboard
                phantom_rank = (leaderboard_prompt_score_final.loc[mask, "mean_crps_score"] <= score).sum() + 1
                # Assign the phantom rank
                leaderboard_prompt_score_final.loc[leaderboard_prompt_score_final["miner_uid"] == uid, "rank_crps"] = phantom_rank

        leaderboard_prompt_score_final = leaderboard_prompt_score_final.sort_values(
            ["rank", "mean_prompt_score"]
        )

        leaderboard_prompt_score_final["rank"] = leaderboard_prompt_score_final["rank"].apply(int)
        leaderboard_prompt_score_final["rank_crps"] = leaderboard_prompt_score_final["rank_crps"].apply(int)
        leaderboard_prompt_score_final["asset"] = "ALL"
        leaderboard_prompt_score_final["time_length"] = time_length
        leaderboard_prompt_score_final["day"] = day
        leaderboard_prompt_score_final["crunch_model"] = leaderboard_prompt_score_final["miner_uid"].isin(crunch_uids)
        leaderboard_prompt_score_final["leaderboard_compute_at"] = datetime.now(timezone.utc)

        print(leaderboard_prompt_score_final)
        cols = ["miner_uid", "player_name", "model", "rank", "mean_prompt_score", "rank_crps", "mean_crps_score", "ratio_max_cap", "asset"]
        print(leaderboard_prompt_score_final[leaderboard_prompt_score_final.crunch_model][cols])

        print("correlation synth/crunch score:", 
                  leaderboard_prompt_score_final[(leaderboard_prompt_score_final.crunch_model) & (leaderboard_prompt_score_final.mean_crunch_score > 0)].iloc[:20][["mean_crps_score", "mean_crunch_score"]].corr().iloc[0, 1])
        
        return leaderboard_prompt_score_final

    def leaderboard_per_asset_col(self, leaderboard_df, crunch_models_id, asset, col, suffix, rank_by="mean", rolling_days: int | None = None):
        """ Leaderboard for one asset and one column """

        if col == "mean_crunch_score":
            df = leaderboard_df[(leaderboard_df.asset==asset) & (leaderboard_df[col] > 0)]
        else:
            df = leaderboard_df[leaderboard_df.asset==asset]

        IDs = ["id"]

        # Optional rolling average (per model, time-aware)
        if rolling_days is not None:
            df = df.sort_values("day")

            n_unique_days = len(df["day"].unique())
            if rolling_days > n_unique_days:
                rolling_days = n_unique_days

            rolled_col = f"{col}_roll{rolling_days}"

            df[rolled_col] = (
                df
                .groupby(IDs)[col]
                .rolling(rolling_days, min_periods=rolling_days)
                .mean()
                .reset_index(level=IDs, drop=True)
            )

            col = rolled_col
            suffix = f"{suffix}_roll{rolling_days}"

        model_stats = (
            df
                .groupby(IDs)
                .agg(
                    mean=(col, "mean"),
                    median=(col, "median"),
                    min=(col, "min"),
                    max=(col, "max"),
                    n_days=("day", "nunique")
                )
                .reset_index()
        )
        model_stats.sort_values(rank_by, ascending=True)

        model_stats = model_stats.rename(columns={k: k+"_"+suffix for k in ["mean", "median", "min", "max"]})

        # Compute rank ignoring crunch miners
        mask = ~model_stats[IDs[0]].isin(crunch_models_id)
        col_rank = rank_by+"_"+suffix
        model_stats.loc[mask, "rank_"+col_rank] = (
            model_stats.loc[mask, col_rank]
                .rank(method="max", ascending=True)
                .astype(int)
        )

        # Assign phantom ranks to crunch miners one by one
        for uid in crunch_models_id:
            if uid in model_stats[IDs[0]].values:
                # Get the score of this crunch miner
                score = model_stats.loc[model_stats[IDs[0]] == uid, col_rank].iloc[0]
                # Count how many miners have smaller scores in the leaderboard
                phantom_rank = (model_stats.loc[mask, col_rank] <= score).sum() + 1
                # Assign the phantom rank
                model_stats.loc[model_stats[IDs[0]] == uid, "rank_"+col_rank] = phantom_rank

        model_stats = model_stats.sort_values(
            ["rank_"+col_rank, col_rank]
        )
        return model_stats, model_stats[model_stats[IDs[0]].isin(crunch_models_id)]

    def compute_leaderboard(self, day: date, df_daily_asset_synth_leaderboard: pd.DataFrame):
        leaderboard = DailySynthLeaderboard.create(df_daily_asset_synth_leaderboard)

        top1 = leaderboard.entries[0].player_name if leaderboard.entries else None
        print(f"Leaderboard created with {len(leaderboard.entries)} positions. TOP 1: {top1}")

        self.daily_synth_leaderboard_repo.save(leaderboard, day)
        self.last_leaderboard = leaderboard

    def compute_summary_last_7_days_leaderboard(self):
        time_length=86400
        leaderboard_df, crunch_df, crunch_models_id = self.daily_synth_leaderboard_repo.get_avg_mean_prompt_score_per_miner(time_length=time_length)

        if leaderboard_df is None or len(leaderboard_df) == 0:
            return

        print("#################################################################")
        print("#################################################################")
        print("Summary: SYNTH leaderboard AVERAGE last 7 days -", "time_length:", time_length)
        print("#################################################################")
        
        # ALL Assets - mean_prompt_score of each day
        print(F"ALL Assets - last 7 days - mean_prompt_score of each day - time length {time_length}")
        asset, col, suffix = "ALL", "mean_prompt_score", "prompt_score"
        all_model_stats, crunch_model_stats = self.leaderboard_per_asset_col(leaderboard_df, crunch_models_id, asset, col, suffix)
        print(crunch_model_stats)
        print()

        # ALL Assets - mean_crps_score of each day
        print(F"ALL Assets - last 7 days - mean_crps_score of each day - time length {time_length}")
        asset, col, suffix = "ALL", "mean_crps_score", "crps_score"
        all_model_stats, crunch_model_stats = self.leaderboard_per_asset_col(leaderboard_df, crunch_models_id, asset, col, suffix)
        print(crunch_model_stats)
        print()
        
        time_length=3600

        leaderboard_df, crunch_df, crunch_models_id = self.daily_synth_leaderboard_repo.get_avg_mean_prompt_score_per_miner(time_length=time_length)

        if leaderboard_df is None or len(leaderboard_df) == 0:
            return
        
        print("#################################################################")
        print("#################################################################")
        print("Summary: SYNTH leaderboard AVERAGE last 7 days -", "time_length:", time_length)
        print("#################################################################")
        
        # ALL Assets - mean_prompt_score of each day
        print(F"ALL Assets - last 7 days - mean_prompt_score of each day - time length {time_length}")
        asset, col, suffix = "ALL", "mean_prompt_score", "prompt_score"
        all_model_stats, crunch_model_stats = self.leaderboard_per_asset_col(leaderboard_df, crunch_models_id, asset, col, suffix)
        print(crunch_model_stats)
        print()

        # ALL Assets - mean_crps_score of each day
        print(F"ALL Assets - last 7 days - mean_crps_score of each day - time length {time_length}")
        asset, col, suffix = "ALL", "mean_crps_score", "crps_score"
        all_model_stats, crunch_model_stats = self.leaderboard_per_asset_col(leaderboard_df, crunch_models_id, asset, col, suffix)
        print(crunch_model_stats)
        print()

    def _compute_missing_days(self, start_day: date, end_day: date, existing_days: set):
        current = start_day
        missing = []

        while current <= end_day:
            if current not in existing_days:
                missing.append(current)
            current += timedelta(days=1)

        return missing
    
    def _score_for_day(self, day: date):
        """
        Run scoring + leaderboard computation for the given day.
        """
        print(f"Backfilling leaderboard for day {day}")

        # score_predictions(day): get synth miners leaderbaord for the day, compute crps for trackers, build daily synth leaderbaord
        df_daily_asset_synth_leaderboard = self.score_predictions(day)

        # self.compute_leaderboard() i.e. add the daily synth leaderbaord to self.daily_synth_leaderboard_repo
        if df_daily_asset_synth_leaderboard is not None:
            self.compute_leaderboard(day, df_daily_asset_synth_leaderboard)


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
            now = datetime.now(timezone.utc)
            # Fetch updated models to ensure the leaderboard contains new models joined since the last execution
            self._refresh_models()
            self._update_prices()

            # Get all daily dates in daily_synth_leaderboard -> existing_days
            existing_days = set(self.daily_synth_leaderboard_repo.get_available_days())
            
            # Get all missing days in daily_synth_leaderboard from 2026-01-23 to now() -> missing_days
            START_DAY = date(2026, 1, 23)
            LAST_DAY = datetime.now(timezone.utc).date() - timedelta(days=1) # always one day of delay

            missing_days = self._compute_missing_days(
                start_day=START_DAY,
                end_day=LAST_DAY,
                existing_days=existing_days,
            )
            print("Missing days:", missing_days)

            if len(missing_days) == 0:
                self.logger.debug("No daily leaderboard to compute")

            # For each day in 'missing_days' apply score_predictions(day)
            for day in missing_days:
                self._score_for_day(day)

            self.compute_summary_last_7_days_leaderboard()

            try:
                end_time = datetime.now(timezone.utc)
                sleep_duration = max(self.SLEEP_TIMEOUT - (end_time - now).total_seconds(), 0)
                self.logger.debug("Sleeping for %d seconds", sleep_duration)
                await asyncio.wait_for(self.stop_event.wait(), timeout=sleep_duration)
            except asyncio.TimeoutError:
                pass

    async def shutdown(self):
        self.stop_event.set()




import numpy as np
from datetime import datetime, timedelta
from scipy import stats as st
from statistics import NormalDist


def simulate_points(
    density_dict: dict,
    current_point: float = 0.0,
    num_simulations: int = 1,
    max_depth: int = 3,
    current_depth: int = 0,
    max_mixtures: int = 5,
    mixture_count: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Simulate 'next point' samples based on a density specification.
    Returns both the sampled values and the 'loc' (mean) values used.

    Supports the same formats as density_pdf:
      1) Scipy distribution
      2) Statistics (NormalDist)
      3) Builtin distribution (via scipy)
      4) Mixture distribution (recursive)

    Parameters
    ----------
    density_dict : dict
        Density specification dictionary.
    current_point : float
        Current point used as a reference (optional).
    num_simulations : int
        Number of samples to draw.
    max_depth : int
        Maximum recursion depth for mixtures.
    current_depth : int
        Current recursion level (internal usage).
    max_mixtures : int
        Maximum total number of mixtures allowed.
    mixture_count : int
        Current count of mixtures encountered.

    Returns
    -------
    samples : np.ndarray
        Simulated values.
    locs : np.ndarray
        Loc (mean) values used in each simulation.
    """

    # --- Check recursion depth
    if current_depth > max_depth:
        raise RecursionError(
            f"Exceeded maximum recursion depth of {max_depth}. "
            "Possible nested mixtures beyond allowed depth."
        )

    dist_type = density_dict.get("type")

    # --- 1) Mixture distribution
    if dist_type == "mixture":
        mixture_count += 1
        if mixture_count > max_mixtures:
            raise ValueError(f"Exceeded maximum mixture count {max_mixtures}")

        components = density_dict["components"]
        weights = np.array([abs(c["weight"]) for c in components], dtype=float)
        weights /= weights.sum()

        # Choose which component each sample comes from
        chosen_idx = np.random.choice(len(components), size=num_simulations, p=weights)

        samples = np.empty(num_simulations)
        locs = np.empty(num_simulations)

        # --- Vectorize: process all samples for each component in a batch
        for j, comp in enumerate(components):
            idx = np.where(chosen_idx == j)[0]
            if len(idx) == 0:
                continue
            sub_spec = comp["density"]
            sub_samples, sub_locs = simulate_points(
                sub_spec,
                current_point=current_point,
                num_simulations=len(idx),
                max_depth=max_depth,
                current_depth=current_depth + 1,
                max_mixtures=max_mixtures,
                mixture_count=mixture_count,
            )
            samples[idx] = sub_samples
            locs[idx] = sub_locs

        return samples, locs

    # --- 2) Scipy distribution
    elif dist_type == "scipy":
        dist_name = density_dict["name"]
        params = density_dict["params"]
        dist_class = getattr(st, dist_name, None)
        if dist_class is None:
            raise ValueError(f"Unknown scipy distribution '{dist_name}'.")
        dist_obj = dist_class(**params)

        loc_val = params.get("loc", 0.0)
        samples = dist_obj.rvs(size=num_simulations)
        locs = np.full(num_simulations, loc_val)
        return samples, locs

    # --- 3) Statistics distribution
    elif dist_type == "statistics":
        bname = density_dict["name"]
        bparams = density_dict["params"]
        if bname == "normal":
            mu = bparams.get("mu", bparams.get("loc", 0.0))
            sigma = bparams.get("sigma", bparams.get("scale", 1.0))
            dist_obj = NormalDist(mu=mu, sigma=sigma)
            samples = np.array(dist_obj.samples(num_simulations))
            locs = np.full(num_simulations, mu)
            return samples, locs
        else:
            raise NotImplementedError(f"Unsupported statistics distribution '{bname}'.")

    # --- 4) Builtin (using scipy fallback)
    elif dist_type == "builtin":
        dist_name = density_dict["name"]
        params = density_dict["params"]
        dist_class = getattr(st, dist_name, None)
        if dist_class is None:
            raise ValueError(f"Unknown builtin distribution '{dist_name}'.")
        dist_obj = dist_class(**params)
        samples = dist_obj.rvs(size=num_simulations)
        locs = np.full(num_simulations, params.get("loc", 0.0))
        return samples, locs

    else:
        raise ValueError(f"Unknown or missing 'type' in density_dict: {density_dict}")
        
def simulate_paths(
    mixture_specs: list,
    start_point: float,
    num_paths: int = 100,
    step_minutes: int = 5,
    start_time: datetime | None = None,
    mode: str = "incremental",  # "absolute", "incremental", "relative"
    quantile_range: list = [0.05, 0.95],
    **simulate_kwargs,
):
    """
    Simulate multiple paths forward given a list of mixture specs for each step.

    Parameters
    ----------
    mixture_specs : list of dict
        Each dict is a valid density spec (mixture, scipy, builtin...), one per step.
    start_point : float
        Initial value at time step 0.
    num_paths : int
        Number of independent paths to simulate.
    step_minutes : int
        Minutes between consecutive steps.
    start_time : datetime, optional
        If provided, returns timestamps instead of integer steps.
    mode : {"absolute", "incremental", "relative"}, default="incremental"
        Determines how simulated values are applied:
        - "absolute" : draw represents an absolute target value
        - "incremental" : draw represents a change (Δ) added to previous value
        - "relative" : draw represents a fractional change
        - "direct" : draw represents the next absolute value directly
    quantile_range : list[float, float], default=[0.05, 0.95]
        Quantile interval to compute for uncertainty bands.
    **simulate_kwargs :
        Extra arguments to pass to simulate_points() (e.g., max_depth, max_mixtures)

    Returns
    -------
    dict
        Dictionary containing:
            "times"       : list of timestamps or integer step indices
            "paths"       : np.ndarray, shape (num_paths, num_steps + 1)
            "mean"        : np.ndarray, mean path value at each step
            "q_low_paths"  : np.ndarray, lower quantile path (quantile_range[0])
            "q_high_paths" : np.ndarray, upper quantile path (quantile_range[1])
    """
    num_steps = len(mixture_specs)
    paths = np.zeros((num_paths, num_steps + 1))
    paths[:, 0] = start_point

    current_points = np.full(num_paths, start_point)

    for t, spec in enumerate(mixture_specs):
        # Simulate all paths for this step
        draws, locs = simulate_points(spec, num_simulations=num_paths, **simulate_kwargs)

        if mode == "absolute":
            # The mixture gives absolute value around loc, so use deviation from loc
            increment = draws - locs
            next_values = current_points + increment
        elif mode == "incremental":
            # The mixture directly represents a change (Δ)
            next_values = current_points + draws
        elif mode == "relative":
            # The mixture represents a fractional change
            next_values = current_points * (1 + draws)
        elif mode == "direct":
            # The mixture draws represent the next absolute value directly
            next_values = draws
        elif mode == "point":
            next_values = draws
        else:
            raise ValueError(f"Unknown mode '{mode}'. Use 'absolute', 'incremental', or 'relative'.")

        paths[:, t + 1] = next_values
        current_points = next_values

    # Build timestamps if requested
    if start_time is not None:
        times = [start_time + timedelta(minutes=step_minutes * i)
                 for i in range(num_steps + 1)]
    else:
        times = list(range(num_steps + 1))

    # --- Compute per-step statistics
    mean_path  = np.mean(paths, axis=0)
    q_low = np.quantile(paths, quantile_range[0], axis=0)
    q_high = np.quantile(paths, quantile_range[1], axis=0)

    return {"times": times, "paths": paths, "mean": mean_path, "q_low_paths": q_low, "q_high_paths": q_high, "quantile_range": quantile_range}


def condition_sum(children, target_sum):
    """
    Enforces sum(children) == target_sum
    Minimal L2 adjustment (optimal transport).
    """
    correction = (target_sum - np.sum(children)) / len(children)
    return children + correction

    
def combine_multiscale_simulations(
    dict_paths: dict,
    step_config: dict
):
    """
    Hierarchical conditional coupling across multiple time resolutions.

    All inputs are INCREMENTS (not prices).

    Parameters
    ----------
    dict_paths : dict[str, np.ndarray]
        Mapping resolution -> array of shape (N, n_steps).
    step_config : dict[str, int]
        Mapping resolution -> step size in seconds.

    Returns
    -------
    final_paths : np.ndarray
        Shape (N, T+1), integrated price paths at finest resolution.
    """

    # --- Sort resolutions from coarse -> fine ---
    levels = sorted(step_config.keys(), key=lambda k: step_config[k], reverse=True)

    # Finest resolution = smallest step
    finest_key = min(step_config, key=step_config.get)

    N = next(iter(dict_paths.values())).shape[0]
    finest_steps = dict_paths[finest_key].shape[1]

    # Working copy (will be progressively constrained)
    constrained = {k: dict_paths[k].copy() for k in levels}

    # --- Enforce constraints top-down ---
    for parent, child in zip(levels[:-1], levels[1:]):
        parent_step = step_config[parent]
        child_step = step_config[child]

        ratio = parent_step // child_step
        if ratio * constrained[parent].shape[1] != constrained[child].shape[1]:
            raise ValueError(f"Incompatible steps between {parent} and {child}")

        for i in range(N):
            for k in range(constrained[parent].shape[1]):
                start = k * ratio
                end = start + ratio

                constrained[child][i, start:end] = condition_sum(
                    constrained[child][i, start:end],
                    constrained[parent][i, k],
                )

    # --- Integrate finest increments ---
    final_increments = constrained[finest_key]
    final_paths = np.zeros((N, finest_steps + 1))
    final_paths[:, 1:] = np.cumsum(final_increments, axis=1)

    return final_paths