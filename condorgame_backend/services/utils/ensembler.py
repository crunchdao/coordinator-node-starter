###############################################
# ENSEMBLER
###############################################
from typing import List, Dict
import copy
from collections import defaultdict
import numpy as np


def get_ensemble_name(config_ensemble):
    ensemble_name = "Ensemble_" + config_ensemble["score"] + "_" + config_ensemble["strategy"]
    if config_ensemble["top_k"] is not None:
        ensemble_name += f"_top_{config_ensemble['top_k']}"

    model_name = ensemble_name[9:]
    return ensemble_name, model_name


def to_builtin(dist):
    """
    Convert a distribution dict of type:
    - scipy
    - statistics
    - builtin
    into a canonical builtin format:
        {"type": "builtin", "name": ..., "params": ...}
    Mixtures are returned unchanged.
    """

    dist_type = dist["type"]

    if dist_type == "mixture":
        return dist  # leave mixture untouched

    # --- builtin → already in the right format ---
    if dist_type == "builtin":
        return dist

    # --- scipy → builtin ---
    if dist_type == "scipy":
        return {
            "type": "builtin",
            "name": dist["name"],     # scipy distribution name
            "params": dist["params"]  # loc/scale/etc
        }

    # --- statistics.normal → builtin:norm ---
    if dist_type == "statistics":
        name = dist["name"]
        params = dist["params"]

        if name == "normal":
            mu = params.get("mu", params.get("loc", 0.0))
            sigma = params.get("sigma", params.get("scale", 1.0))

            return {
                "type": "builtin",
                "name": "norm",
                "params": {"loc": mu, "scale": sigma}
            }

        raise NotImplementedError(
            f"statistics distribution '{name}' not supported"
        )

    raise ValueError(f"Unknown distribution type: {dist_type}")

def ensure_mixture(dist):
    """
    Convert non-mixture distribution into mixture with 1 component.
    Assumes dist is already converted to builtin format.
    """
    if dist["type"] == "mixture":
        return dist

    # Wrap builtin (or converted scipy/statistics) into mixture
    return {
        "type": "mixture",
        "components": [
            {
                "density": dist,
                "weight": 1.0
            }
        ]
    }


def ensemble_tracker_distributions(
    tracker_distributions: Dict[str, Dict[str, List[Dict]]],
    tracker_scores: Dict[str, float] = None,
    config: dict = {"strategy": "uniform"},
) -> Dict[str, List[Dict]]:
    """
    Combine multiple tracker distributions into a single ensemble distribution.

    /!/ Input: All distributions must have SUCCESS status /!/

    Each tracker provides predicted distributions at multiple time resolutions and steps.
    This function merges them using a specified weighting strategy.

    Parameters
    ----------
    tracker_distributions : Dict[str, Dict[str, List[Dict]]]
        A dictionary mapping tracker names to their predicted distributions.
        Structure:
            {
                tracker_name: {
                    resolution_1: [dist_step_0, dist_step_1, ...],
                    resolution_2: [dist_step_0, dist_step_1, ...],
                    ...
                },
                ...
            }
        Each `dist_step_*` should be a dictionary representing a probability distribution

    tracker_scores : Dict[str, float], optional
        Dictionary mapping tracker names to their current performance scores.
        Required for weighted strategies (e.g., 'score_weighted', 'softmax', 'winner', 'rank_weighted').
        If not provided or empty, the 'uniform' strategy is used.

    config : dict, optional
        Configuration dictionary. Supported keys:
            - strategy : str
                Weighting strategy. Options:
                    - "uniform": all trackers equally weighted
                    - "score_weighted": weight proportional to tracker_scores
                    - "softmax": softmax of tracker_scores, controlled by 'temperature'
                    - "winner": only the highest-scoring tracker is used
                    - "rank_weighted": weight inversely proportional to tracker rank
            - temperature : float
                Temperature parameter for 'softmax' strategy (default: 1.0)
            - top_k : int
                Optional: consider only the top-K trackers by score before applying weights

    Returns
    -------
    Dict[str, List[Dict]]
        Ensemble distributions per resolution. Structure:
            {
                resolution_1: [step_0_ensemble, step_1_ensemble, ...],
                resolution_2: [step_0_ensemble, step_1_ensemble, ...],
                ...
            }

    Notes
    -----
    - If 'top_k' is specified, trackers not in the top-K by score are ignored.
    - Each tracker distribution is wrapped as a mixture component, and its weight
      is multiplied by the tracker weight.
    - Component weights are normalized to sum to 1 per step.
    - Errors during distribution conversion or weighting are caught and logged; 
      processing continues with remaining trackers/components.
    - Designed to work with predictions from multiple trackers at multiple resolutions.
    """

    # Extract tracker names and a sample distribution for structure reference
    tracker_names = list(tracker_distributions.keys())
    example_dists = next(iter(tracker_distributions.values()))

    # ---------------------------------------------------------
    # Clean tracker_scores: drop NaN / non-finite scores
    # ---------------------------------------------------------
    tracker_scores_copy = None
    if tracker_scores is not None:

        tracker_scores_copy = tracker_scores.copy()

        tracker_scores_copy = {
            t: s for t, s in tracker_scores_copy.items()
            if s is not None and np.isfinite(s)
        }

        tracker_names = [name for name in tracker_names if name in tracker_scores_copy]

    # ---------------------------------------------------------
    # Optional TOP-K filtering BEFORE strategy weighting
    # ---------------------------------------------------------
    if config.get("top_k", None) is not None:
        K = config["top_k"]
        if tracker_scores_copy is None or len(tracker_scores_copy) == 0:
            raise ValueError("top_k requires tracker_scores")

        # Sort trackers by score descending and pick top-K
        ranked = sorted(tracker_scores_copy.items(), key=lambda x: x[1], reverse=True)
        top_k_names = [t for t, _ in ranked[:K]]

        # Keep only trackers in top-K
        tracker_names = [t for t in tracker_names if t in top_k_names]

        # Safety: ensure at least one tracker remains
        if len(tracker_names) == 0:
            raise ValueError("top_k filtered out all trackers!")
        
    if tracker_scores_copy is not None:
        tracker_scores_copy = {k:v for k,v in tracker_scores_copy.items() if k in tracker_names}

    # ---------------------------------------------------------
    # Compute tracker weights based on selected strategy
    # ---------------------------------------------------------
    if config["strategy"] == "uniform" or tracker_scores_copy is None or len(tracker_scores_copy) == 0:
        # All trackers equally weighted
        weights = {t: 1.0 / len(tracker_names) for t in tracker_names}

    elif config["strategy"] == "score_weighted":
        # Weight proportional to score
        total = sum(tracker_scores_copy.values())
        weights = {t: tracker_scores[t] / total if total > 0 else 1.0 / len(tracker_names) for t in tracker_names}

    elif config["strategy"] == "softmax":
        # Softmax weighting
        temperature = config.get("temperature", 1.0)
        s = np.array([tracker_scores_copy[t] for t in tracker_names])
        w = np.exp(s / temperature)
        w /= w.sum()
        weights = {t: float(w[i]) for i, t in enumerate(tracker_names)}

    elif config["strategy"] == "winner":
        # Only the top-scoring tracker gets weight 1
        best = max(tracker_scores_copy, key=lambda t: tracker_scores_copy[t])
        weights = {t: 1.0 if t == best else 0.0 for t in tracker_names}
    
    elif config["strategy"] == "rank_weighted":
        # Weight inversely proportional to rank (1st rank gets highest)
        ranked = sorted(tracker_scores_copy.items(), key=lambda x: x[1], reverse=True)
        weights = {t: 1.0 / (rank + 1) for rank, (t, _) in enumerate(ranked)}
        # Normalize weights
        total_weight = sum(weights[t] for t in tracker_names)
        weights = {t: weights[t] / total_weight for t in tracker_names}

    else:
        raise ValueError(f"Unknown strategy: {config["strategy"]}")

    # ---------------------------------------------------------
    # Build ensemble distributions for each resolution and step
    # ---------------------------------------------------------
    ensemble_distributions = {}
    resolutions = example_dists.keys()

    for resolution in resolutions:
        ensemble_distributions_resolution = []
        n_steps = len(example_dists[resolution])
        
        for step_idx in range(n_steps):
            step_ensemble = {
                "step": example_dists[resolution][step_idx]["step"],
                "type": "mixture",
                "components": []
            }
    
            # Collect all components from all trackers for this step
            for t in tracker_names:
                try:
                    raw_dist = tracker_distributions[t][resolution][step_idx]
                except Exception as e:
                    print(f"[Ensemble] ERROR: Cannot read distribution for tracker '{t}' at resolution {resolution} and step {step_idx}: {e}")
                    continue
    
                # try:
                #     # 1) Convert to builtin
                #     builtin_dist = to_builtin(raw_dist)
                # except Exception as e:
                #     print(f"[Ensemble] ERROR: Failed to convert tracker '{t}' distribution to builtin at resolution {resolution} and step {step_idx}: {e}")
                #     # Optionally log raw_dist for debugging
                #     # print("Raw distribution:", raw_dist)
                #     continue
                builtin_dist = raw_dist
    
                try:
                    # 2) Wrap as single-component mixture
                    dist = ensure_mixture(builtin_dist)
                except Exception as e:
                    print(f"[Ensemble] ERROR: ensure_mixture failed for tracker '{t}' at resolution {resolution} and step {step_idx}: {e}")
                    continue
    
                try:
                    # 3) Add weighted components
                    for comp in dist.get("components", []):
                        try:
                            new_comp = copy.deepcopy(comp)
                            new_comp["weight"] *= weights[t]
    
                            if new_comp["weight"] > 0:
                                step_ensemble["components"].append(new_comp)
    
                        except Exception as e:
                            print(f"[Ensemble] ERROR: Failed applying weight to component of tracker '{t}' at resolution {resolution} and step {step_idx}: {e}")
                            continue
    
                except Exception as e:
                    print(f"[Ensemble] ERROR: Failed processing mixture for tracker '{t}' at resolution {resolution} and step {step_idx}: {e}")
                    continue
    
    
            # Normalize mixture weights to sum to 1
            total_weight = sum(c["weight"] for c in step_ensemble["components"])
            if total_weight > 0:
                for c in step_ensemble["components"]:
                    c["weight"] /= total_weight
    
            ensemble_distributions_resolution.append(step_ensemble)

        ensemble_distributions[resolution] = ensemble_distributions_resolution

    return ensemble_distributions, weights