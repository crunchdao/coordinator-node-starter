from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from typing import Any

import requests

BTC_USD_PYTH_FEED_ID = "0xe62df6c8b4a85fe1cc8b337a5f8854d9c1f5f59e4cb4ce8b063a492f6ed5b5b6"


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
    resolved_client = client or _build_client_from_env()
    latest = resolved_client.get_latest_price(BTC_USD_PYTH_FEED_ID)
    if latest is None:
        return {}

    return {
        "asset": "BTC",
        "price": latest["price"],
        "confidence": latest["confidence"],
        "publish_time": latest["publish_time"],
        "feed_id": latest["feed_id"],
        "source": "pyth",
        "as_of": now.isoformat(),
    }


def validate_probability_up_output(inference_output: dict[str, Any]) -> dict[str, Any]:
    if "p_up" not in inference_output:
        raise ValueError("inference_output must contain 'p_up'")

    p_up = float(inference_output["p_up"])
    if p_up < 0.0 or p_up > 1.0:
        raise ValueError("'p_up' must be within [0, 1]")

    return {"p_up": p_up}


def resolve_ground_truth_from_pyth(prediction: Any, client: PythHermesClient | None = None) -> dict[str, Any] | None:
    if str(getattr(prediction, "asset", "")).upper() != "BTC":
        return None

    entry_price = (getattr(prediction, "inference_input", {}) or {}).get("price")
    if entry_price is None:
        return None

    try:
        entry_price_value = float(entry_price)
    except Exception:
        return None

    resolved_client = client or _build_client_from_env()
    latest = resolved_client.get_latest_price(BTC_USD_PYTH_FEED_ID)
    if latest is None:
        return None

    resolved_price = float(latest["price"])

    return {
        "asset": "BTC",
        "entry_price": entry_price_value,
        "resolved_price": resolved_price,
        "entry_publish_time": (getattr(prediction, "inference_input", {}) or {}).get("publish_time"),
        "resolved_publish_time": latest.get("publish_time"),
        "y_up": resolved_price > entry_price_value,
        "source": "pyth",
    }


def score_brier_probability_up(prediction: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    try:
        p_up = float(prediction["p_up"])
        if p_up < 0.0 or p_up > 1.0:
            raise ValueError("'p_up' must be within [0, 1]")

        y_up = bool(ground_truth["y_up"])
        y_value = 1.0 if y_up else 0.0
        brier_loss = (p_up - y_value) ** 2

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
