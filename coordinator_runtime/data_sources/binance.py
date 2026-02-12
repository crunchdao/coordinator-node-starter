from __future__ import annotations

from datetime import datetime
from math import log, sqrt
import json
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:  # pragma: no cover - exercised via injected client in tests
    from binance.client import Client as BinanceSDKClient
except Exception:  # pragma: no cover - keep compatibility if package unavailable
    BinanceSDKClient = None

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def fetch_binance_klines(
    symbol: str,
    interval: str,
    limit: int,
    *,
    client: Any | None = None,
) -> list[dict[str, float]]:
    sdk_client = client or _build_public_binance_client()
    if sdk_client is not None:
        payload = sdk_client.get_klines(symbol=symbol, interval=interval, limit=int(limit))
        return _parse_klines_payload(payload)

    query = urlencode({"symbol": symbol, "interval": interval, "limit": int(limit)})
    request = Request(
        f"{BINANCE_KLINES_URL}?{query}",
        headers={"User-Agent": "coordinator-runtime-binance/1.0"},
    )

    with urlopen(request, timeout=8.0) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))

    return _parse_klines_payload(payload)


def fetch_recent_closes_from_binance(symbol: str, count: int, interval: str = "1m") -> list[float]:
    candles = fetch_binance_klines(symbol=symbol, interval=interval, limit=count)
    closes: list[float] = []
    for candle in candles:
        value = candle.get("close")
        if _is_positive_number(value):
            closes.append(float(value))
    return closes


def provide_binance_raw_input(
    now: datetime,
    *,
    symbol: str,
    interval: str = "1m",
    window_minutes: int = 120,
    horizon_minutes: int = 5,
    fetch_klines: Callable[[str, str, int], list[dict[str, float]]] | None = None,
) -> dict[str, object]:
    _ = now
    fetcher = fetch_klines or fetch_binance_klines

    try:
        candles = fetcher(symbol, interval, window_minutes)
    except Exception:
        candles = _fallback_candles(window_minutes)

    if not candles:
        candles = _fallback_candles(window_minutes)

    candles = [row for row in candles if isinstance(row, dict)]
    if not candles:
        candles = _fallback_candles(window_minutes)

    return {
        "symbol": symbol,
        "asof_ts": int(candles[-1].get("ts", int(datetime.now().timestamp()))),
        "horizon_minutes": int(horizon_minutes),
        "candles_1m": candles[-window_minutes:],
    }


def resolve_binance_ground_truth(
    prediction: Any,
    *,
    symbol: str,
    horizon_minutes: int = 5,
    interval: str = "1m",
    fetch_recent_closes: Callable[[str, int, str], list[float]] | None = None,
) -> dict[str, object]:
    inference_input = getattr(prediction, "inference_input", {}) or {}
    candles = inference_input.get("candles_1m") if isinstance(inference_input, dict) else None
    anchor_price = _extract_anchor_close(candles)

    if anchor_price is None or anchor_price <= 0.0:
        return {
            "return_5m": 0.0,
            "volatility_5m": 0.0,
            "meta": {"reason": "missing_anchor_price"},
        }

    fetcher = fetch_recent_closes or fetch_recent_closes_from_binance
    count = int(horizon_minutes) + 1

    try:
        closes = fetcher(symbol, count, interval)
    except Exception:
        closes = [anchor_price] * count

    closes = [float(x) for x in closes if _is_positive_number(x)]
    if len(closes) < count:
        closes = ([anchor_price] * (count - len(closes))) + closes

    resolved_close = closes[-1]
    realized_return = log(resolved_close / anchor_price)

    one_minute_returns = [
        log(closes[idx] / closes[idx - 1])
        for idx in range(1, len(closes))
        if closes[idx - 1] > 0.0 and closes[idx] > 0.0
    ]
    trailing = one_minute_returns[-int(horizon_minutes) :]
    realized_vol = sqrt(sum(value * value for value in trailing)) if trailing else 0.0

    return {
        "return_5m": realized_return,
        "volatility_5m": realized_vol,
        "meta": {
            "symbol": symbol,
            "horizon_minutes": int(horizon_minutes),
            "anchor_close": anchor_price,
            "resolved_close": resolved_close,
        },
    }


def _extract_anchor_close(candles) -> float | None:
    if not isinstance(candles, list) or not candles:
        return None

    last = candles[-1]
    if not isinstance(last, dict):
        return None

    close = last.get("close")
    if not _is_positive_number(close):
        return None

    return float(close)


def _fallback_candles(limit: int) -> list[dict[str, float]]:
    base = 45_000.0
    candles: list[dict[str, float]] = []
    ts0 = int(datetime.now().timestamp()) - int(limit) * 60

    for idx in range(limit):
        close = base * (1.0 + 0.0001 * idx)
        candles.append(
            {
                "ts": ts0 + idx * 60,
                "open": close * 0.9995,
                "high": close * 1.0005,
                "low": close * 0.9990,
                "close": close,
                "volume": 1000.0 + idx,
            }
        )

    return candles


def _is_positive_number(value: Any) -> bool:
    try:
        parsed = float(value)
    except Exception:
        return False

    return parsed > 0.0


def _build_public_binance_client() -> Any | None:
    if BinanceSDKClient is None:
        return None

    try:
        return BinanceSDKClient(
            api_key=None,
            api_secret=None,
            requests_params={"timeout": 8.0},
            ping=False,
        )
    except Exception:
        return None


def _parse_klines_payload(payload: Any) -> list[dict[str, float]]:
    if not isinstance(payload, list):
        return []

    rows: list[dict[str, float]] = []
    for entry in payload:
        if not isinstance(entry, list) or len(entry) < 6:
            continue

        try:
            rows.append(
                {
                    "ts": int(entry[0]) // 1000,
                    "open": float(entry[1]),
                    "high": float(entry[2]),
                    "low": float(entry[3]),
                    "close": float(entry[4]),
                    "volume": float(entry[5]),
                }
            )
        except Exception:
            continue

    return rows
