###############################################
# Synth CRPS scoring
###############################################
# https://github.com/mode-network/synth-subnet/blob/4da15db6a8ccab84b0faa3b7acc0574ffbe3ee21/synth/validator/crps_calculation.py#L12

import numpy as np
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