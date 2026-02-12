from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import erf, sqrt
import os
from typing import Any

import requests

from coordinator.plugins.schemas import BtcGroundTruthSchema, BtcRawInputSchema, BtcScopeSchema, ProbabilityUpOutputSchema

BTC_USD_PYTH_FEED_ID = "0xe62df6c8b4a85fe1cc8b337a5f8854d9c1f5f59e4cb4ce8b063a492f6ed5b5b6"

_FALLBACK_PRICE = 45_000.0
_FALLBACK_TICK = 0


@dataclass
class PythHermesClient:
    base_url: str = "https://hermes.pyth.network"
    timeout_seconds: float = 5.0

    def get_latest_price(self, feed_id: str) -> dict[str, Any] | None:
        response = requests.get(
            f"{self.base_url.rstrip('/')}/v2/updates/price/latest",
            params={"ids[]": feed_id, "parsed": "true"},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()

        payload = response.json()
        parsed = payload.get("parsed") or []
        if not parsed:
            return None

        price_info = parsed[0].get("price") or {}
        return {
            "price": _decode_price(price_info),
            "confidence": _decode_confidence(price_info),
            "publish_time": int(price_info.get("publish_time", 0)),
            "feed_id": feed_id,
        }


def build_raw_input_from_pyth(now: datetime, client: PythHermesClient | None = None) -> dict[str, Any]:
    """Return BTC tick payload compatible with existing benchmark trackers.

    The payload shape matches `PriceData` expected by TrackerBase.tick:
    {"BTC": [(ts, price), ...]}
    """
    resolved_client = client or _build_client_from_env()
    latest = _get_latest_price_or_fallback(resolved_client, now)

    ts = int(now.timestamp())
    price = float(latest["price"])
    confidence = abs(float(latest.get("confidence", 0.0)))

    # Build a tiny synthetic history so starter benchmark models can compute variance immediately.
    # (3 points, 5-minute spacing, non-zero variance in returns)
    delta = max(confidence, abs(price) * 0.0001, 1e-6)
    payload = {
        "BTC": [
            (ts - 600, price - 1.75 * delta),
            (ts - 300, price - 0.5 * delta),
            (ts, price),
        ]
    }
    return BtcRawInputSchema.model_validate(payload).model_dump()


def validate_probability_up_output(inference_output: dict[str, Any]) -> dict[str, Any]:
    """Accept direct p_up output or derive p_up from density output."""
    p_up = _extract_probability_up(inference_output)
    if p_up is None:
        raise ValueError("inference_output must contain a valid 'p_up' or a parseable density payload")

    normalized = ProbabilityUpOutputSchema.model_validate({"p_up": p_up})
    return normalized.model_dump()


def resolve_ground_truth_from_pyth(prediction: Any, client: PythHermesClient | None = None) -> dict[str, Any] | None:
    prediction_scope = getattr(prediction, "scope", {}) or {}

    try:
        parsed_scope = BtcScopeSchema.model_validate(prediction_scope)
    except Exception:
        return None

    if parsed_scope.asset.upper() != "BTC":
        return None

    entry_price = _extract_entry_price(getattr(prediction, "inference_input", {}) or {})
    if entry_price is None:
        return None

    resolved_client = client or _build_client_from_env()
    latest = _get_latest_price_or_fallback(resolved_client, datetime.now())
    resolved_price = float(latest["price"])

    truth = {
        "asset": "BTC",
        "entry_price": float(entry_price),
        "resolved_price": resolved_price,
        "resolved_publish_time": latest.get("publish_time"),
        "y_up": resolved_price > float(entry_price),
        "source": latest.get("source", "pyth"),
    }
    return BtcGroundTruthSchema.model_validate(truth).model_dump()


def score_brier_probability_up(prediction: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    try:
        p_up = _extract_probability_up(prediction)
        if p_up is None:
            raise ValueError("could not extract p_up from prediction payload")

        normalized_prediction = ProbabilityUpOutputSchema.model_validate({"p_up": p_up})
        normalized_truth = BtcGroundTruthSchema.model_validate(ground_truth)

        y_value = 1.0 if normalized_truth.y_up else 0.0
        brier_loss = (normalized_prediction.p_up - y_value) ** 2

        return {
            "value": 1.0 - brier_loss,
            "success": True,
            "failed_reason": None,
        }
    except Exception as exc:
        return {
            "value": None,
            "success": False,
            "failed_reason": str(exc),
        }


def score_position_return_probability_up(prediction: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    """Score each prediction as realized strategy return.

    - p_up in [0, 1] becomes position in [-1, 1]
    - realized market return = (resolved_price - entry_price) / entry_price
    - strategy return = position * realized market return
    """
    try:
        p_up = _extract_probability_up(prediction)
        if p_up is None:
            raise ValueError("could not extract p_up from prediction payload")

        normalized_prediction = ProbabilityUpOutputSchema.model_validate({"p_up": p_up})
        normalized_truth = BtcGroundTruthSchema.model_validate(ground_truth)

        if normalized_truth.entry_price is None or normalized_truth.resolved_price is None:
            raise ValueError("ground truth must include entry_price and resolved_price")

        entry_price = float(normalized_truth.entry_price)
        resolved_price = float(normalized_truth.resolved_price)
        if entry_price <= 0.0:
            raise ValueError("entry_price must be > 0")

        market_return = (resolved_price - entry_price) / entry_price
        position = (2.0 * normalized_prediction.p_up) - 1.0
        strategy_return = position * market_return

        return {
            "value": float(strategy_return),
            "success": True,
            "failed_reason": None,
        }
    except Exception as exc:
        return {
            "value": None,
            "success": False,
            "failed_reason": str(exc),
        }


def _extract_probability_up(prediction: dict[str, Any]) -> float | None:
    if "p_up" in prediction:
        return float(prediction["p_up"])

    raw = prediction.get("result")
    if isinstance(raw, list) and raw:
        p = _extract_probability_from_distribution(raw[0])
        if p is not None:
            return p

    return None


def _extract_probability_from_distribution(distribution: dict[str, Any]) -> float | None:
    dist_type = distribution.get("type")

    if dist_type == "mixture":
        components = distribution.get("components") or []
        if not components:
            return None

        total_weight = 0.0
        weighted_probability = 0.0

        for component in components:
            weight = float(component.get("weight", 0.0))
            density = component.get("density") or {}
            probability = _extract_probability_from_density(density)
            if probability is None:
                continue

            weighted_probability += weight * probability
            total_weight += weight

        if total_weight <= 0.0:
            return None

        return weighted_probability / total_weight

    return _extract_probability_from_density(distribution)


def _extract_probability_from_density(density: dict[str, Any]) -> float | None:
    if density.get("type") != "builtin":
        return None
    if density.get("name") != "norm":
        return None

    params = density.get("params") or {}
    loc = float(params.get("loc", 0.0))
    scale = float(params.get("scale", 0.0))

    if scale <= 0.0:
        if loc > 0.0:
            return 1.0
        if loc < 0.0:
            return 0.0
        return 0.5

    z = loc / scale
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def _extract_entry_price(inference_input: dict[str, Any]) -> float | None:
    btc_entries = inference_input.get("BTC")
    if isinstance(btc_entries, list) and btc_entries:
        last = btc_entries[-1]
        if isinstance(last, (list, tuple)) and len(last) >= 2:
            return float(last[1])

    if "price" in inference_input:
        return float(inference_input["price"])

    return None


def _get_latest_price_or_fallback(client: PythHermesClient, now: datetime) -> dict[str, Any]:
    try:
        latest = client.get_latest_price(BTC_USD_PYTH_FEED_ID)
        if latest is not None:
            return {**latest, "source": "pyth"}
    except Exception:
        pass

    return _fallback_price_payload(now)


def _fallback_price_payload(now: datetime) -> dict[str, Any]:
    global _FALLBACK_PRICE, _FALLBACK_TICK

    _FALLBACK_TICK += 1
    drift = float(((_FALLBACK_TICK % 7) - 3) * 3.0)
    _FALLBACK_PRICE = max(1_000.0, _FALLBACK_PRICE + drift)

    return {
        "price": _FALLBACK_PRICE,
        "confidence": max(abs(drift) * 0.2, 1.0),
        "publish_time": int(now.timestamp()),
        "feed_id": BTC_USD_PYTH_FEED_ID,
        "source": "fallback-synthetic",
    }


def _build_client_from_env() -> PythHermesClient:
    base_url = os.getenv("PYTH_HERMES_URL", "https://hermes.pyth.network")
    timeout_seconds = float(os.getenv("PYTH_TIMEOUT_SECONDS", "5"))
    return PythHermesClient(base_url=base_url, timeout_seconds=timeout_seconds)


def _decode_price(price_info: dict[str, Any]) -> float:
    raw = int(price_info.get("price", 0))
    expo = int(price_info.get("expo", 0))
    return float(raw) * (10 ** expo)


def _decode_confidence(price_info: dict[str, Any]) -> float:
    raw = int(price_info.get("conf", 0))
    expo = int(price_info.get("expo", 0))
    return float(raw) * (10 ** expo)
