###############################################
# SIMULATE PATHS
###############################################

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