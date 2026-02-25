# Vanta Trading Competition — Build Spec

## Overview

Build a Crunch coordinator that replicates the [Vanta Network miner game](https://github.com/taoshidev/vanta-network/blob/main/docs/miner.md) as a competition. Models are traders — they receive 1m candle data + their current positions, and return leveraged LONG/SHORT/FLAT orders. The coordinator tracks positions, applies fees, scores PnL, enforces lifecycle rules, and ranks models on a leaderboard.

This builds on the existing coordinator-node-starter framework. We customize the challenge package (model interface, scoring) and add node extensions (position manager, fee engine, lifecycle manager).

---

## Design Principles

1. **Models implement predict().** `tick()` is the base class framework method (not overridden). `predict()` uses `self.candles` + `self.positions` → returns `Order | None`. Candle history accumulates model-side in the base class; positions come from the coordinator. If a model crashes/restarts, the coordinator re-sends backfill candles and current positions.
2. **Only 1m candles.** Single feed, single granularity. No 5m/15m/1h aggregation. Keep it simple.
3. **All constants from env vars.** Every Vanta parameter (leverage limits, fee rates, lifecycle thresholds) is read from environment variables with sensible defaults.
4. **Typed everything.** Dataclasses for domain objects, Pydantic for framework contracts, type hints on every signature.
5. **Coordinator owns position state.** The scoring function is a thin passthrough — all PnL computation happens in the PositionManager extension.

---

## 0. Pre-requisite Refactors

Before building Vanta, clean up the existing code to establish proper layer separation.

### 0a. Slim down FeedReader — feed layer only fetches candles

**Current problem:** `FeedReader.get_input()` does too much — loads 1m candles, aggregates to 5m/15m/1h, loads orderbook, loads funding. This belongs in the predict service (or not at all for Vanta).

**Changes to `coordinator_node/services/feed_reader.py`:**
- Remove `MULTI_TF` aggregation logic (`_aggregate_candles`, candles_5m/15m/1h generation)
- Remove `_load_latest_microstructure` (orderbook/funding)
- `get_input()` returns just `{symbol, asof_ts, candles_1m: [list of candle dicts]}` — raw 1m candles from DB, nothing more
- Add `get_latest_candles(subjects: list[str], limit: int = 1) -> dict[str, list[dict]]` — returns latest N candles per symbol from feed_records. This is what the predict worker needs.

**Changes to `coordinator_node/services/feed_data.py`:**
- Remove `_microstructure_loop` (depth + funding polling)
- Remove `microstructure_enabled` / `microstructure_poll_seconds` from `FeedDataSettings`
- Feed data service just ingests 1m candles. Period.

**Changes to `coordinator_node/feeds/providers/binance.py`:**
- Keep `_fetch_candles` and `_fetch_ticks` (needed)
- Keep `_fetch_depth` and `_fetch_funding` (don't remove — other competitions might use them)
- No changes needed here, the feed provider is fine — it's the service layer that's doing too much

**Tests:** Existing feed tests should still pass. Update any that assert multi-TF or microstructure fields in `get_input()` output.

### 0b. Per-model arguments via gRPC callable

**Current problem:** `runner.call()` broadcasts identical arguments to all models. Vanta needs per-model positions.

**Solution:** The `model-runner-client` already supports this. `DynamicSubclassModelRunner.call()` accepts `arguments` as a `Callable[[ModelRunner], tuple]` — the callable receives the model runner instance (which has `.model_id`) and returns per-model arguments.

**Changes to `coordinator_node/services/predict.py`:**
- Add `_encode_tick_per_model(market_data, positions_by_model)` that returns a callable:

```python
def _encode_tick_per_model(self, market_data: dict, positions_by_model: dict[str, dict]):
    """Return a callable that resolves per-model tick arguments at call time.
    
    The model-runner-client calls this with each ModelRunner instance,
    allowing us to inject per-model positions while broadcasting the same market data.
    """
    def resolve(model_runner):
        model_id = str(model_runner.model_id)
        positions = positions_by_model.get(model_id, {})
        return ([
            Argument(position=1, data=Variant(type=VariantType.JSON, value=encode_data(VariantType.JSON, market_data))),
            Argument(position=2, data=Variant(type=VariantType.JSON, value=encode_data(VariantType.JSON, positions))),
        ], [])
    return resolve
```

- Update `_tick_models()` to accept per-model positions and use this callable
- The `call_method` config specifies `method="tick"` with two JSON args

**No changes to model-runner-client.** This uses existing API.

---

## Architecture

```
challenge/                              # pip-installable participant package
  vanta/
    __init__.py                         # re-exports Order, TrackerBase
    types.py                            # Order dataclass
    tracker.py                          # TrackerBase with tick() interface
    scoring.py                          # score_prediction() passthrough
    config.py                           # package metadata
    examples/
      __init__.py
      sma_crossover.py                  # SMA crossover on BTCUSDT
      mean_reversion.py                 # Bollinger Band reversion on ETHUSDT
      volatility_breakout.py            # Low-vol breakout across pairs

node/
  config/
    crunch_config.py                    # CrunchConfig (types, predictions, callables, behavior)
    callables.env                       # scoring function callable path
  extensions/
    __init__.py
    position_manager.py                 # Order → Position → Portfolio → Snapshot (DB-backed)
    fee_engine.py                       # Carry (scheduled), spread, slippage
    lifecycle_manager.py                # IMMUNITY → CHALLENGE → MAINCOMP → PROBATION → ELIMINATED
  db/
    tables/
      trading.py                        # OrderRow, PositionRow, PortfolioRow (new tables)
    trading_repositories.py             # DB access for orders, positions, portfolios
  api/
    __init__.py
    positions.py                        # Custom REST endpoints for position/lifecycle state
  deployment/
    model-orchestrator-local/
      config/
        starter-submission/             # example model
        models.dev.yml
      data/submissions/
        starter-submission/             # deployed copy
  scripts/
    verify_e2e.py
  docker-compose.yml
  Dockerfile
  Makefile
  .local.env

tests/                                  # pytest suite (top-level, NOT inside node/ or challenge/)
  __init__.py
  test_position_manager.py
  test_fee_engine.py
  test_lifecycle_manager.py
  test_scoring.py
  test_tracker.py
```

---

## 1. Model Interface — `challenge/vanta/tracker.py`

```python
import pandas as pd
from collections import deque
from vanta.types import Order

CANDLE_WINDOW = 180  # 3 hours of 1m candles


class TrackerBase:
    """Base class for competition models. Implement predict() to compete.

    The coordinator calls tick() via gRPC every minute with one new candle
    per asset + current positions. tick() is a base class method that:
      1. Appends the candle to self.candles[symbol] (rolling pd.DataFrame)
      2. Updates self.positions from the coordinator's position state
      3. Calls self.predict() — YOUR method
      4. Returns the serialized Order (or None) back over gRPC
    """

    def __init__(self) -> None:
        self._buffers: dict[str, deque[dict]] = {}  # raw candle dicts per symbol
        self.candles: dict[str, pd.DataFrame] = {}   # DataFrames built from buffers
        self.positions: dict[str, dict] = {}          # updated each tick by coordinator

    def tick(self, market_data: dict, positions: dict) -> dict | None:
        """Framework method — called via gRPC each minute. Do NOT override.

        Args:
            market_data: One new candle per symbol.
                         {"BTCUSDT": {"open": 67000, "high": 67100, "low": 66900,
                                      "close": 67050, "volume": 123.4, "timestamp": 1700000000},
                          "ETHUSDT": {...}}
            positions:   Current open positions keyed by trade_pair.
                         {"BTCUSDT": {"direction": "LONG", "leverage": 0.5,
                                      "entry_price": 67123.4, "unrealized_pnl": 0.003}}
                         Empty dict = no open positions.

        Returns:
            Serialized Order dict or None.
        """
        # 1. Append one candle per symbol to rolling buffer
        for symbol, candle in (market_data or {}).items():
            if symbol not in self._buffers:
                self._buffers[symbol] = deque(maxlen=CANDLE_WINDOW)
            self._buffers[symbol].append(candle)
            self.candles[symbol] = pd.DataFrame(list(self._buffers[symbol]))

        # 2. Update positions from coordinator state
        self.positions = positions or {}

        # 3. Call participant's predict()
        order = self.predict()
        if order is None:
            return None

        return {"action": order.action, "trade_pair": order.trade_pair, "leverage": order.leverage}

    def predict(self) -> Order | None:
        """Return an Order or None. Override this.

        Use self.candles (dict[str, pd.DataFrame]) and self.positions (dict[str, dict])
        to make trading decisions.

        self.candles:
            Rolling 1m OHLCV DataFrames keyed by symbol.
            Columns: open, high, low, close, volume, timestamp
            Up to 180 rows (3 hours). Grows from first tick.

        self.positions:
            Current open positions keyed by trade_pair.
            Example: {"BTCUSDT": {"direction": "LONG", "leverage": 0.5,
                                   "entry_price": 67123.4, "unrealized_pnl": 0.003}}
            Empty dict = no open positions.
        """
        raise NotImplementedError
```

### Key decisions:

- **`tick()` is the base class framework method** — receives one candle per asset over gRPC (tiny JSON payload), accumulates state internally, calls `predict()`. Participants never override it.
- **`predict()` is what participants implement** — no arguments, uses `self.candles` and `self.positions`. Returns `Order | None`.
- **`self.candles` is `dict[str, pd.DataFrame]`** — quants get `.rolling()`, `.pct_change()`, `.ewm()`, TA-lib, etc. out of the box.
- **`self.positions` is `dict[str, dict]`** — simple. `if "BTCUSDT" in self.positions:`.
- **State accumulates model-side** in the base class. If model restarts, coordinator re-sends backfill candles via repeated `tick()` calls to rebuild the window.
- **Wire payload is minimal** — one candle dict per symbol per minute (~6 symbols × 6 fields = tiny). No need to send 180-row history every call.

### Wire format (two JSON args via gRPC):

**Arg 1 — `market_data`:** one candle per symbol
```json
{
  "BTCUSDT": {"open": 67000, "high": 67100, "low": 66900, "close": 67050, "volume": 123.4, "timestamp": 1700000000},
  "ETHUSDT": {"open": 3500, "high": 3510, "low": 3490, "close": 3505, "volume": 456.7, "timestamp": 1700000000}
}
```

**Arg 2 — `positions`:** current open positions (or `{}`)
```json
{
  "BTCUSDT": {"direction": "LONG", "leverage": 0.5, "entry_price": 67123.4, "unrealized_pnl": 0.003}
}
```

### gRPC call method:

The coordinator calls `tick(market_data, positions)` with two JSON arguments:

```python
call_method = CallMethodConfig(
    method="tick",
    args=[
        CallMethodArg(name="market_data", type="JSON"),
        CallMethodArg(name="positions", type="JSON"),
    ],
)
```

No `subject`/`resolve_horizon_seconds`/`step_seconds` — those are prediction-contest concepts. This is a trading game.

---

## 2. Types — `challenge/vanta/types.py`

```python
from dataclasses import dataclass

SUPPORTED_PAIRS: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
VALID_ACTIONS: set[str] = {"LONG", "SHORT", "FLAT"}


@dataclass
class Order:
    action: str           # LONG, SHORT, FLAT
    trade_pair: str       # must be in SUPPORTED_PAIRS
    leverage: float = 0.0 # 0.001–2.5 for crypto; ignored for FLAT

    def __post_init__(self):
        if self.action not in VALID_ACTIONS:
            raise ValueError(f"action must be one of {VALID_ACTIONS}, got {self.action!r}")
        if self.trade_pair not in SUPPORTED_PAIRS:
            raise ValueError(f"trade_pair must be one of {SUPPORTED_PAIRS}, got {self.trade_pair!r}")
        if self.action != "FLAT" and not (0.001 <= self.leverage <= 2.5):
            raise ValueError(f"leverage must be 0.001–2.5, got {self.leverage}")
```

---

## 3. CrunchConfig — `node/config/crunch_config.py`

### Pydantic contracts:

```python
class RawInput(BaseModel):
    """What the Binance feed produces each minute."""
    model_config = ConfigDict(extra="allow")
    symbol: str = "BTCUSDT"
    asof_ts: int = 0
    candles_1m: list[dict] = Field(default_factory=list)  # [{open, high, low, close, volume, timestamp}]

## Note: no InferenceInput model needed.
## tick() receives two raw JSON args (market_data, positions) directly.
## The coordinator encodes them as two gRPC Argument(type=JSON) values.

class InferenceOutput(BaseModel):
    """What models return (serialized Order or null)."""
    model_config = ConfigDict(extra="allow")
    action: str = "FLAT"
    trade_pair: str = "BTCUSDT"
    leverage: float = 0.0

class ScoreResult(BaseModel):
    """What scoring produces — portfolio snapshot from PositionManager."""
    model_config = ConfigDict(extra="allow")
    value: float = 0.0               # net_pnl (primary ranking metric)
    portfolio_value: float = 1.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    drawdown_pct: float = 0.0
    portfolio_leverage: float = 0.0
    open_positions: int = 0
    order_accepted: bool = True
    order_rejected_reason: str | None = None
    success: bool = True
    failed_reason: str | None = None
```

### CrunchConfig:

```python
class CrunchConfig(BaseCrunchConfig):
    raw_input_type = RawInput
    # input_type not set — tick() receives raw JSON args directly, no InferenceInput model
    output_type = InferenceOutput
    score_type = ScoreResult

    scope = PredictionScope(subject="BTCUSDT", step_seconds=60)

    # tick(market_data, positions) — two JSON args
    call_method = CallMethodConfig(
        method="tick",
        args=[
            CallMethodArg(name="market_data", type="JSON"),
            CallMethodArg(name="positions", type="JSON"),
        ],
    )

    aggregation = Aggregation(
        windows={"pnl_24h": AggregationWindow(hours=24), "pnl_72h": AggregationWindow(hours=72), "pnl_7d": AggregationWindow(hours=168)},
        ranking_key="pnl_24h",
        ranking_direction="desc",
    )
```

### Data flow (two workers):

```
Feed worker:
  Binance 1m klines → FeedDataRecord → DB

Predict worker (each minute):
  1. Read latest 1m candle per symbol from feed_records
  2. Read open positions per model from positions table
  3. Call tick(market_data, positions) on each model via gRPC
     → model-side: TrackerBase.tick() accumulates candle, calls predict()
     → returns {action, trade_pair, leverage} or None
  4. Store prediction (status=PENDING) with raw order as inference_output

Score worker (each cycle):
  1. Pick up PENDING predictions
  2. PositionManager.process_order() for each → updates orders/positions/portfolios tables
  3. Write score with portfolio snapshot, mark prediction SCORED
  4. Apply carry fees, mark-to-market, lifecycle checks
  5. Write snapshots, rebuild leaderboard
```

### How the predict worker builds tick() args:

1. Reads the latest 1m candle per symbol from feed_records → `market_data` dict (same for all models)
2. Reads open positions for ALL active models from `positions` table → `positions_by_model` dict
3. Uses `_encode_tick_per_model(market_data, positions_by_model)` which returns a **callable**
4. Passes the callable to `runner.call("tick", arguments=callable)` — the model-runner-client resolves per-model positions at call time via `callable(model_runner)` using `model_runner.model_id`
5. All models receive the same `market_data` but each gets only its own `positions`

This is a single concurrent broadcast — all models called in parallel, but each gets personalized position data.

Candle history accumulation happens **model-side** in `TrackerBase.tick()` (rolling deque → DataFrame). The coordinator only sends one candle per symbol per minute.

On model restart, the coordinator sends backfill candles via repeated `tick()` calls to rebuild the model's internal window.

---

## 4. Position Manager — `node/extensions/position_manager.py`

Maintains a `PortfolioState` per model with open_positions and closed_positions. This is the core engine.

### Data structures (all dataclasses, all typed):

```python
@dataclass
class TrackedOrder:
    action: str
    trade_pair: str
    leverage: float
    timestamp: int
    price: float
    spread_fee: float = 0.0
    slippage_fee: float = 0.0
    accepted: bool = True
    rejected_reason: str | None = None

@dataclass
class TrackedPosition:
    trade_pair: str
    direction: str          # LONG, SHORT
    leverage: float
    entry_price: float
    entry_ts: int
    max_seen_leverage: float = 0.0
    carry_fees: float = 0.0
    spread_fees: float = 0.0
    slippage_fees: float = 0.0
    realized_pnl: float = 0.0
    is_open: bool = True
    close_ts: int | None = None
    close_price: float | None = None

    def unrealized_pnl(self, current_price: float) -> float:
        direction_sign = 1.0 if self.direction == "LONG" else -1.0
        return direction_sign * self.leverage * (current_price - self.entry_price) / self.entry_price

    @property
    def total_fees(self) -> float:
        return self.carry_fees + self.spread_fees + self.slippage_fees

    def net_pnl(self, current_price: float) -> float:
        pnl = self.realized_pnl if not self.is_open else self.unrealized_pnl(current_price)
        return pnl - self.total_fees

@dataclass
class PortfolioState:
    model_id: str
    open_positions: dict[str, TrackedPosition]    # keyed by trade_pair
    closed_positions: list[TrackedPosition]
    peak_value: float = 1.0
    current_value: float = 1.0
    last_order_ts: dict[str, int]                 # per trade_pair cooldown tracking
    registration_ts: int = 0
```

### PositionManager class:

```python
class PositionManager:
    def __init__(
        self,
        fee_engine: FeeEngine,
        supported_pairs: list[str] = SUPPORTED_PAIRS,
        position_leverage_min: float = 0.001,      # POSITION_LEVERAGE_MIN env var
        position_leverage_max: float = 2.5,         # POSITION_LEVERAGE_MAX env var
        portfolio_leverage_max: float = 5.0,         # PORTFOLIO_LEVERAGE_MAX env var
        order_cooldown_seconds: int = 10,            # ORDER_COOLDOWN_SECONDS env var
    ): ...

    def process_order(
        self,
        model_id: str,
        order_dict: dict | None,    # None = model chose inaction
        current_prices: dict[str, float],  # {symbol: price}
        ts: int,
    ) -> dict:
        """Process an order and return a portfolio snapshot dict matching ScoreResult."""
        ...

    def get_positions_for_model(self, model_id: str) -> dict[str, dict]:
        """Return simplified position view for passing to model's tick()."""
        ...
```

### Order processing rules (Vanta parity):

1. `None` order → skip to snapshot (mark-to-market update, no execution)
2. Validate: action ∈ {LONG, SHORT, FLAT}, pair supported, cooldown not active (10s per pair), leverage ≥ min
3. Execute:
   - **FLAT** → close position, book realized PnL
   - **New position** → create with clamped leverage (per-position max, portfolio max)
   - **Same direction** → increase leverage, weighted-average entry price
   - **Opposite direction, partial** → reduce leverage
   - **Opposite direction, full+** → close existing (book PnL), open remainder in opposite direction
4. Apply spread fee (`spread_rate × order_leverage`) and slippage fee (`slippage_bps/10000 × order_leverage`) at order time
5. Return snapshot dict matching `ScoreResult`

### Position rules:
- Max 1 open position per pair per model
- 10-second cooldown between orders on same pair
- Leverage below minimum → **rejected** (not clamped)
- Leverage above maximum → **clamped** (not rejected)
- Portfolio leverage (sum of all open) → **clamped** (not rejected)

---

## 5. Fee Engine — `node/extensions/fee_engine.py`

| Fee      | Rate          | When                                | Formula                                              |
|----------|---------------|-------------------------------------|------------------------------------------------------|
| Spread   | 0.1%          | Each order                          | `SPREAD_FEE_RATE × order_leverage`                   |
| Slippage | 3 bps         | Each order                          | `(SLIPPAGE_BPS / 10000) × order_leverage`            |
| Carry    | 10.95% annual | Every 8h (04:00, 12:00, 20:00 UTC) | `(daily_rate × max_seen_leverage) / periods_per_day` |

Carry uses `max_seen_leverage` ever on that position, not current leverage. Applied once per carry hour (deduplicated).

```python
class FeeEngine:
    def __init__(
        self,
        spread_fee_rate: float = 0.001,       # SPREAD_FEE_RATE
        slippage_bps: float = 3.0,             # SLIPPAGE_BPS
        carry_annual_rate: float = 0.1095,     # CARRY_ANNUAL_RATE
        carry_interval_hours: int = 8,         # CARRY_INTERVAL_HOURS
        carry_times_utc: list[str] = ["04:00", "12:00", "20:00"],  # CARRY_TIMES_UTC
    ): ...

    def compute_spread_fee(self, leverage: float) -> float: ...
    def compute_slippage_fee(self, leverage: float) -> float: ...
    def should_apply_carry(self, model_id: str, trade_pair: str, ts: int) -> bool: ...
    def apply_carry_fees(self, portfolio: PortfolioState, ts: int) -> float: ...
```

---

## 6. Lifecycle Manager — `node/extensions/lifecycle_manager.py`

State machine per model:

```
Register → IMMUNITY (4h) → CHALLENGE (90d) → MAINCOMP → (optional) PROBATION (60d) → ELIMINATED
```

| State      | Entry                   | Duration  | Exit                                                                      |
|------------|-------------------------|-----------|---------------------------------------------------------------------------|
| IMMUNITY   | Registration            | 4 hours   | Auto → CHALLENGE                                                          |
| CHALLENGE  | After immunity          | 90 days   | Pass: 61+ trading days, DD < 10%, rank ≤ 25 → MAINCOMP. Fail → ELIMINATED |
| MAINCOMP   | Pass challenge          | Ongoing   | DD > 10% → ELIMINATED. Rank drops below 25 → PROBATION                    |
| PROBATION  | Demoted from MAINCOMP   | 60 days   | Recover to top 25 → MAINCOMP. Timeout → ELIMINATED                        |
| ELIMINATED | Any elimination trigger | Permanent | Blacklisted, cannot re-register                                           |

Probation/rank rules only activate when `MIN_MODELS_FOR_PROBATION` (default 10) models are competing.

```python
class LifecycleManager:
    def __init__(
        self,
        immunity_hours: int = 4,
        challenge_period_days: int = 90,
        challenge_min_trading_days: int = 61,
        max_drawdown_pct: float = 10.0,
        probation_days: int = 60,
        probation_rank_cutoff: int = 25,
        min_models_for_probation: int = 10,
    ): ...

    def register_model(self, model_id: str, ts: int) -> ModelLifecycle: ...
    def update(self, model_id: str, drawdown_pct: float, rank: int, trading_days: int, total_models: int, ts: int) -> ModelLifecycle: ...
    def is_in_immunity(self, model_id: str, ts: int) -> bool: ...
    def get_active_models(self) -> list[ModelLifecycle]: ...
    def get_summary(self) -> dict: ...
```

---

## 7. Scoring — `challenge/vanta/scoring.py`

Thin passthrough. The PositionManager has already computed the portfolio snapshot.

```python
def score_prediction(prediction: dict, ground_truth: dict) -> dict:
    """Extract portfolio snapshot from prediction. Ground truth not used (already marked to market)."""
    snapshot = prediction.get("portfolio_snapshot", {})
    return {
        "value": snapshot.get("net_pnl", 0.0),
        "portfolio_value": snapshot.get("portfolio_value", 1.0),
        "unrealized_pnl": snapshot.get("unrealized_pnl", 0.0),
        "realized_pnl": snapshot.get("realized_pnl", 0.0),
        "total_fees": snapshot.get("total_fees", 0.0),
        "gross_pnl": snapshot.get("gross_pnl", 0.0),
        "net_pnl": snapshot.get("net_pnl", 0.0),
        "drawdown_pct": snapshot.get("drawdown_pct", 0.0),
        "portfolio_leverage": snapshot.get("portfolio_leverage", 0.0),
        "open_positions": snapshot.get("open_positions", 0),
        "order_accepted": snapshot.get("order_accepted", True),
        "order_rejected_reason": snapshot.get("order_rejected_reason"),
        "success": True,
        "failed_reason": None,
    }
```

---

## 8. Database Tables — Position State

Three new tables alongside the existing pipeline tables (`inputs`, `predictions`, `scores`, `snapshots`, `leaderboards`):

### `orders` — append-only audit log of every order submitted

| Column | Type | Description |
|--------|------|-------------|
| `id` | str (PK) | `ORD_{model_id}_{ts}` |
| `model_id` | str (FK → models, indexed) | Which model submitted this |
| `action` | str | LONG, SHORT, FLAT |
| `trade_pair` | str (indexed) | BTCUSDT, ETHUSDT, etc. |
| `leverage` | float | Requested leverage |
| `price` | float | Execution price (candle close at time of order) |
| `spread_fee` | float | Spread fee charged |
| `slippage_fee` | float | Slippage fee charged |
| `accepted` | bool | Whether order was executed |
| `rejected_reason` | str \| None | Why rejected (cooldown, invalid pair, etc.) |
| `prediction_id` | str (FK → predictions) | Links back to the prediction record |
| `created_at` | datetime (indexed) | When order was processed |

### `positions` — one row per model × trade_pair (open + closed)

| Column | Type | Description |
|--------|------|-------------|
| `id` | str (PK) | `POS_{model_id}_{trade_pair}_{entry_ts}` |
| `model_id` | str (FK → models, indexed) | |
| `trade_pair` | str (indexed) | |
| `direction` | str | LONG, SHORT |
| `leverage` | float | Current leverage |
| `entry_price` | float | Weighted-average entry price |
| `entry_ts` | datetime | When position was opened |
| `max_seen_leverage` | float | Highest leverage ever (for carry fee calc) |
| `carry_fees` | float | Accumulated carry fees |
| `spread_fees` | float | Total spread fees on this position |
| `slippage_fees` | float | Total slippage fees on this position |
| `realized_pnl` | float | Gross P&L from price movement (set at close) |
| `net_pnl` | float | `realized_pnl - total_fees` (set at close) |
| `is_open` | bool (indexed) | True while position is active |
| `close_price` | float \| None | Exit price |
| `close_ts` | datetime \| None | When position was closed |
| `updated_at` | datetime | Last modification |

### `portfolios` — one mutable row per model (current state)

| Column | Type | Description |
|--------|------|-------------|
| `model_id` | str (PK, FK → models) | |
| `peak_value` | float | High-water mark for drawdown calculation |
| `current_value` | float | Latest mark-to-market portfolio value |
| `total_realized_pnl` | float | Sum of all closed position P&L |
| `total_fees` | float | Sum of all fees ever paid |
| `registration_ts` | datetime | When model entered competition |
| `last_order_ts_jsonb` | dict (JSONB) | `{trade_pair: timestamp}` for cooldown tracking |
| `lifecycle_state` | str | IMMUNITY, CHALLENGE, MAINCOMP, PROBATION, ELIMINATED |
| `lifecycle_changed_at` | datetime | When state last changed |
| `trading_days` | int | Number of days with at least one trade |
| `elimination_reason` | str \| None | Why eliminated (if applicable) |
| `updated_at` | datetime | Last update |

### How tables relate:

```
models (existing)
  ├── predictions (existing) ── orders (new, 1:1 with prediction)
  ├── portfolios (new, 1:1 with model — current state)
  └── positions (new, 1:N — all open + closed positions)

feed_records (existing) → read for current prices
snapshots (existing) → periodic portfolio summaries for leaderboard
leaderboards (existing) → ranked by aggregated snapshots
```

### PositionManager loads state from DB on startup:

```python
# On score worker startup:
portfolios = db.query(PortfolioRow).all()
open_positions = db.query(PositionRow).filter(is_open=True).all()
# Reconstruct in-memory PortfolioState per model from these rows
# From here, all mutations go through PositionManager → written back to DB
```

---

## 9. Integration: Score Worker Flow

The score worker owns the PositionManager, FeeEngine, and LifecycleManager. It runs on a loop (every ~60s or on pg NOTIFY). The predict worker is unchanged — it just calls models and stores predictions with the raw order output.

### Predict worker (modified for per-model positions):

```
1. Feed worker: Binance 1m kline → FeedDataRecord → DB
2. Predict worker wakes:
   a. Reads latest 1m candle per symbol from feed_records → market_data dict
   b. Reads active model IDs from portfolios table (lifecycle_state != ELIMINATED)
   c. Reads ALL open positions grouped by model_id → positions_by_model dict
   d. Builds callable = _encode_tick_per_model(market_data, positions_by_model)
   e. Calls runner.call("tick", arguments=callable) — single concurrent broadcast,
      each model gets same market_data but own positions via callable(model_runner)
   f. Stores prediction with status=PENDING:
      - If model returned Order: inference_output={action, trade_pair, leverage}
      - If model returned None: inference_output={} (empty dict) — score worker
        will still mark-to-market and write a snapshot, just no order processed
```

### Score worker (extended — owns position + lifecycle state):

```
1. Read latest prices from feed_records (latest 1m candle close per symbol)

2. Process new orders:
   a. Pick up predictions with status=PENDING
   b. For each prediction:
      - Extract order from inference_output (action, trade_pair, leverage) or None
      - PositionManager.process_order(model_id, order, prices, ts)
      - Write order row → orders table
      - Update position row → positions table (open/close/modify)
      - Update portfolio row → portfolios table (current_value, peak_value, fees, etc.)
      - Write score with portfolio snapshot → scores table
      - Mark prediction as SCORED

3. Apply carry fees (if due):
   - Check if current time crosses 04:00, 12:00, or 20:00 UTC since last cycle
   - FeeEngine.apply_carry_fees() on all open positions
   - Update position rows (carry_fees) and portfolio rows (total_fees, current_value)

4. Mark-to-market ALL models (even those that didn't trade this cycle):
   - For each model with open positions:
     - Recompute unrealized_pnl on each position with latest prices
     - Recompute portfolio current_value and drawdown_pct
     - Update portfolio row

5. Lifecycle enforcement:
   - For each model:
     - Read drawdown_pct from portfolio
     - Read current rank from latest leaderboard
     - Read trading_days from portfolio
     - LifecycleManager.update(model_id, drawdown_pct, rank, trading_days, total_models, ts)
     - If state changed → update portfolio row (lifecycle_state, lifecycle_changed_at)
     - If ELIMINATED → log reason, mark portfolio (elimination_reason)
   - Eliminated models are excluded from future tick() calls by predict worker

6. Write snapshots:
   - Per-model periodic summary → snapshots table (existing)
   - Feeds into aggregation windows (pnl_24h, pnl_72h, pnl_7d)

7. Rebuild leaderboard:
   - From latest snapshots, rank by pnl_24h desc
   - Write to leaderboards table (existing)
   - Exclude ELIMINATED models
```

### Why this split works:

- **Predict worker** stays simple: get data → call models → store raw output. No position logic.
- **Score worker** is the single owner of position state. No race conditions — one process reads orders, processes them, updates positions, applies fees, checks lifecycle, writes scores.
- **DB is the source of truth.** If score worker restarts, it reloads state from `portfolios` + `positions` tables and picks up pending predictions.
- **Existing tables unchanged.** `predictions`, `scores`, `snapshots`, `leaderboards` all work as before. We just added three new tables and changed what the score worker does between reading predictions and writing scores.

---

## 10. API Endpoints — `node/api/positions.py`

FastAPI router at `/positions`:

| Endpoint                             | Description                                                 |
|--------------------------------------|-------------------------------------------------------------|
| GET /positions/rules                 | Full competition rules (leverage, fees, lifecycle, scoring) |
| GET /positions/pairs                 | Supported pairs and limits                                  |
| GET /positions/models                | All models with position summaries                          |
| GET /positions/models/{id}           | Detailed model view                                         |
| GET /positions/models/{id}/positions | Open and closed positions                                   |
| GET /positions/models/{id}/orders    | Paginated order history                                     |
| GET /positions/models/{id}/lifecycle | Lifecycle state                                             |
| GET /positions/lifecycle/summary     | Models grouped by state                                     |

Start as stubs returning the correct shape. Integration with live state is a future extension.

---

## 11. Example Models

### Starter Submission (deployed as default model):

```python
from vanta import TrackerBase, Order

class SmaModel(TrackerBase):
    def predict(self) -> Order | None:
        df = self.candles.get("BTCUSDT")
        if df is None or len(df) < 20:
            return None

        fast = df["close"].rolling(5).mean().iloc[-1]
        slow = df["close"].rolling(20).mean().iloc[-1]

        if "BTCUSDT" not in self.positions:
            if fast > slow:
                return Order("LONG", "BTCUSDT", leverage=0.5)
            elif fast < slow:
                return Order("SHORT", "BTCUSDT", leverage=0.5)
        else:
            pos = self.positions["BTCUSDT"]
            if pos["direction"] == "LONG" and fast < slow:
                return Order("FLAT", "BTCUSDT")
            elif pos["direction"] == "SHORT" and fast > slow:
                return Order("FLAT", "BTCUSDT")

        return None
```

### 3 example strategies in `challenge/vanta/examples/`:

1. **SMA Crossover** (`sma_crossover.py`) — dual SMA on BTCUSDT (starter above)
2. **Mean Reversion** (`mean_reversion.py`) — Bollinger Band reversion on ETHUSDT
3. **Volatility Breakout** (`volatility_breakout.py`) — monitors vol across pairs, trades low-vol breakouts

Each must demonstrate:
- Returning `Order(...)` for a trade
- Returning `None` for no action
- Using `self.positions` to check current state before trading
- Using `self.candles` with DataFrame ops (`.rolling()`, `.std()`, etc.)

---

## 12. Configuration — `node/.local.env`

```env
# Feed
FEED_SOURCE=binance
FEED_SUBJECTS=BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,ADAUSDT
FEED_KIND=candle
FEED_GRANULARITY=1m
FEED_POLL_SECONDS=5
FEED_BACKFILL_MINUTES=180

# Leverage
POSITION_LEVERAGE_MIN=0.001
POSITION_LEVERAGE_MAX=2.5
PORTFOLIO_LEVERAGE_MAX=5.0
ORDER_COOLDOWN_SECONDS=10
STEP_SECONDS=60

# Fees
CARRY_ANNUAL_RATE=0.1095
CARRY_INTERVAL_HOURS=8
CARRY_TIMES_UTC=04:00,12:00,20:00
SPREAD_FEE_RATE=0.001
SLIPPAGE_BPS=3

# Lifecycle
CHALLENGE_PERIOD_DAYS=90
CHALLENGE_MIN_TRADING_DAYS=61
MAX_DRAWDOWN_PCT=10.0
PROBATION_DAYS=60
PROBATION_RANK_CUTOFF=25
MIN_MODELS_FOR_PROBATION=10
IMMUNITY_HOURS=4

# Scoring
SCORING_FUNCTION=vanta.scoring:score_prediction

# Candle accumulator
CANDLE_WINDOW_SIZE=180
```

---

## 13. TDD Testing Plan

Follow strict Red-Green-Refactor. Write each test first, watch it fail, then implement the minimal code to pass. Build bottom-up: types → fee engine → position manager → lifecycle → scoring → DB → integration.

All tests use real objects. No mocks except for DB session (use SQLite in-memory) and gRPC (not tested here — integration tested via verify_e2e.py).

### Phase 1: Types + TrackerBase (no dependencies)

**File: `tests/test_types.py`**

Build Order first — everything else depends on it.

```
RED:  test_order_long_valid — Order("LONG", "BTCUSDT", 0.5) creates without error
GREEN: dataclass with fields, no validation
RED:  test_order_invalid_action — Order("BUY", "BTCUSDT", 0.5) raises ValueError
GREEN: add action validation in __post_init__
RED:  test_order_invalid_pair — Order("LONG", "INVALID", 0.5) raises ValueError
GREEN: add trade_pair validation
RED:  test_order_leverage_too_low — Order("LONG", "BTCUSDT", 0.0001) raises ValueError
GREEN: add leverage range check
RED:  test_order_leverage_too_high — Order("LONG", "BTCUSDT", 3.0) raises ValueError
GREEN: already passes (range check covers it)... if it passes, tighten the test
RED:  test_order_flat_ignores_leverage — Order("FLAT", "BTCUSDT", 0.0) creates without error
GREEN: skip leverage check when action == FLAT
```

**File: `tests/test_tracker.py`**

Build TrackerBase. Depends on Order.

```
RED:  test_predict_raises_not_implemented — TrackerBase().predict() raises NotImplementedError
GREEN: predict() method with raise NotImplementedError

RED:  test_tick_accumulates_single_candle — call tick() with one BTCUSDT candle,
      assert self.candles["BTCUSDT"] is a DataFrame with 1 row, correct columns
GREEN: tick() creates deque, appends, builds DataFrame

RED:  test_tick_accumulates_multiple_candles — call tick() 3 times,
      assert DataFrame has 3 rows in order
GREEN: already passes if accumulation works

RED:  test_tick_rolls_window — call tick() 181 times (CANDLE_WINDOW=180),
      assert DataFrame has exactly 180 rows, oldest dropped
GREEN: deque(maxlen=CANDLE_WINDOW)

RED:  test_tick_multiple_symbols — tick with BTCUSDT + ETHUSDT candles,
      assert both keys exist in self.candles with independent DataFrames
GREEN: per-symbol buffer keying

RED:  test_tick_updates_positions — tick with positions={"BTCUSDT": {...}},
      assert self.positions matches
GREEN: self.positions = positions or {}

RED:  test_tick_calls_predict_returns_order — subclass that returns Order("LONG", "BTCUSDT", 0.5),
      assert tick() returns {"action": "LONG", "trade_pair": "BTCUSDT", "leverage": 0.5}
GREEN: call predict(), serialize Order to dict

RED:  test_tick_calls_predict_returns_none — subclass that returns None,
      assert tick() returns None
GREEN: if order is None: return None
```

### Phase 2: Fee Engine (pure math, no DB)

**File: `tests/test_fee_engine.py`**

```
RED:  test_spread_fee — compute_spread_fee(leverage=1.0) == 0.001 (rate × leverage)
GREEN: return self.spread_fee_rate * leverage

RED:  test_spread_fee_half_leverage — compute_spread_fee(0.5) == 0.0005
GREEN: already passes

RED:  test_slippage_fee — compute_slippage_fee(leverage=1.0) == 0.0003 (3bps)
GREEN: return (self.slippage_bps / 10000) * leverage

RED:  test_carry_should_apply_at_0400_utc — ts at 04:00 UTC → should_apply_carry() == True
GREEN: parse carry_times_utc, check hour match

RED:  test_carry_should_not_apply_at_0500_utc — ts at 05:00 UTC → False
GREEN: already passes

RED:  test_carry_deduplication — call should_apply_carry twice at same 04:00 → True then False
GREEN: track last_carry_ts per model:pair

RED:  test_carry_fee_amount — position with max_seen_leverage=1.0, annual_rate=0.1095
      → daily_rate=0.0003, 3 periods/day → fee = 0.0001 per period
GREEN: (annual_rate / 365 * max_seen_leverage) / periods_per_day

RED:  test_carry_uses_max_seen_leverage — position opened at lev=1.0, reduced to 0.5,
      carry still computed on 1.0
GREEN: read max_seen_leverage from position, not current leverage

RED:  test_apply_carry_fees_updates_positions — portfolio with 2 open positions,
      apply_carry at 04:00 → both positions' carry_fees increase
GREEN: iterate open positions, add fee to each
```

### Phase 3: Position Manager (core engine, no DB yet — pure in-memory)

**File: `tests/test_position_manager.py`**

PositionManager takes FeeEngine as constructor arg. Tests use a real FeeEngine.

```
--- Opening positions ---

RED:  test_open_long — process_order(model, {action:LONG, trade_pair:BTCUSDT, leverage:0.5},
      prices={BTCUSDT: 50000}, ts) → snapshot with order_accepted=True,
      get_positions_for_model shows BTCUSDT LONG
GREEN: create PortfolioState, create TrackedPosition, return snapshot

RED:  test_open_short — same but SHORT, verify direction
GREEN: already works if direction is read from order

RED:  test_none_order_no_position_change — process_order(model, None, ...) → snapshot computed,
      open_positions=0 if no prior position
GREEN: skip execution when order is None, return mark-to-market snapshot

--- Leverage validation ---

RED:  test_leverage_below_min_rejected — leverage=0.0001 → order_accepted=False,
      rejected_reason contains "minimum"
GREEN: validate leverage >= min before execution

RED:  test_leverage_above_max_clamped — leverage=5.0 → order_accepted=True,
      position leverage == 2.5 (max), NOT rejected
GREEN: clamp leverage = min(leverage, position_leverage_max)

RED:  test_portfolio_leverage_clamped — model already has 4.0 leverage across positions,
      new order with leverage=2.0 → clamped to 1.0 (portfolio max=5.0)
GREEN: compute portfolio total, clamp new order

--- Position modification ---

RED:  test_same_direction_increases_leverage — open LONG 0.5, then LONG 0.3 →
      position leverage=0.8, entry_price is weighted average
GREEN: detect same direction, weighted avg formula

RED:  test_opposite_direction_partial_reduces — open LONG 1.0, then SHORT 0.3 →
      position still LONG with leverage=0.7
GREEN: detect opposite, reduce leverage

RED:  test_opposite_direction_exceeds_flips — open LONG 0.5, then SHORT 0.8 →
      old position closed (realized PnL booked), new SHORT 0.3 opened
GREEN: close existing, open remainder in opposite direction

RED:  test_flat_closes_position — open LONG 0.5, then FLAT → position closed,
      realized_pnl computed, no open positions
GREEN: close position on FLAT

RED:  test_flat_no_position_rejected — FLAT on pair with no open position →
      order_accepted=False
GREEN: check position exists before FLAT

--- Cooldown ---

RED:  test_cooldown_same_pair — two orders on BTCUSDT 5 seconds apart → second rejected
GREEN: track last_order_ts per pair, reject if ts - last < cooldown

RED:  test_cooldown_different_pair — order BTCUSDT then ETHUSDT immediately → both accepted
GREEN: cooldown is per-pair

--- P&L calculation ---

RED:  test_long_profit — open LONG at 50000, price moves to 51000,
      unrealized_pnl = leverage * (51000-50000)/50000
GREEN: direction_sign * leverage * (current - entry) / entry

RED:  test_long_loss — open LONG at 50000, price drops to 49000
GREEN: already works (negative pnl)

RED:  test_short_profit — open SHORT at 50000, price drops to 49000 → positive pnl
GREEN: direction_sign = -1 for SHORT

RED:  test_short_loss — open SHORT at 50000, price rises to 51000 → negative pnl
GREEN: already works

--- Fees at order time ---

RED:  test_fees_applied_on_open — open LONG leverage=1.0 → position has
      spread_fees=0.001, slippage_fees=0.0003
GREEN: call fee_engine.compute_spread/slippage, add to position

--- Drawdown ---

RED:  test_drawdown_tracking — portfolio starts at 1.0, gains to 1.1 (peak=1.1),
      then drops to 1.0 → drawdown_pct = 9.09%
GREEN: track peak_value, compute (peak - current) / peak * 100

--- Multi-model ---

RED:  test_multi_model_independence — model_A opens LONG, model_B opens SHORT,
      model_A's positions unaffected by model_B
GREEN: per-model PortfolioState keying

--- Unsupported/invalid ---

RED:  test_unsupported_pair_rejected — order on "DOGEBTC" → rejected
GREEN: validate pair in supported_pairs

RED:  test_no_price_rejected — order on BTCUSDT but prices dict has no BTCUSDT → rejected
GREEN: check price exists before execution
```

### Phase 4: Lifecycle Manager (pure state machine, no DB)

**File: `tests/test_lifecycle_manager.py`**

```
RED:  test_register_starts_immunity — register_model(ts=0) → state=IMMUNITY
GREEN: create ModelLifecycle with state=IMMUNITY

RED:  test_immunity_auto_transitions — register at ts=0, update at ts=4h+1s →
      state=CHALLENGE
GREEN: check elapsed > immunity_hours

RED:  test_immunity_blocks_elimination — register at ts=0, drawdown=50% at ts=1h →
      state still IMMUNITY (not eliminated)
GREEN: skip elimination check during IMMUNITY

RED:  test_drawdown_eliminates_from_challenge — state=CHALLENGE, drawdown=11% →
      state=ELIMINATED, reason contains "drawdown"
GREEN: check drawdown > max in CHALLENGE state

RED:  test_drawdown_eliminates_from_maincomp — same from MAINCOMP
GREEN: check drawdown in MAINCOMP too

RED:  test_challenge_pass — state=CHALLENGE, 90 days elapsed, 61 trading days,
      rank=10, drawdown=5% → state=MAINCOMP
GREEN: check all pass criteria

RED:  test_challenge_fail_insufficient_days — 90 days elapsed, only 30 trading days → ELIMINATED
GREEN: check min trading days

RED:  test_challenge_fail_bad_rank — 90 days, 61 days, rank=30 → ELIMINATED
GREEN: check rank <= cutoff

RED:  test_maincomp_rank_drop_probation — state=MAINCOMP, rank=30,
      total_models=15 (>= MIN_MODELS) → state=PROBATION
GREEN: check rank > cutoff when enough models

RED:  test_maincomp_rank_drop_ignored_few_models — state=MAINCOMP, rank=30,
      total_models=5 (< MIN_MODELS) → still MAINCOMP
GREEN: skip rank check when total_models < min

RED:  test_probation_recovery — state=PROBATION, rank improves to 10 → MAINCOMP
GREEN: check rank <= cutoff → transition back

RED:  test_probation_timeout — state=PROBATION, 60 days elapsed, rank still 30 → ELIMINATED
GREEN: check elapsed > probation_days

RED:  test_eliminated_cannot_reregister — register model that was eliminated → error/rejected
GREEN: check blacklist before register
```

### Phase 5: Scoring (thin passthrough)

**File: `tests/test_scoring.py`**

```
RED:  test_score_extracts_net_pnl — prediction with portfolio_snapshot={net_pnl: 0.05, ...}
      → score_prediction returns {value: 0.05, net_pnl: 0.05, ...}
GREEN: extract from snapshot dict

RED:  test_score_empty_snapshot — prediction with portfolio_snapshot={} →
      value=0.0, all defaults
GREEN: .get() with defaults

RED:  test_score_all_fields_present — verify all ScoreResult fields in output
GREEN: already passes if extraction covers all fields
```

### Phase 6: DB Tables + Repositories (SQLite in-memory)

**File: `tests/test_trading_repositories.py`**

Use `sqlmodel` with `sqlite://` for fast tests. No Postgres needed.

```
RED:  test_save_and_load_order — create OrderRow, save, query by id → matches
GREEN: OrderRow model + repository save/get

RED:  test_save_and_load_position_open — PositionRow with is_open=True, save, load → matches
GREEN: PositionRow model + repository

RED:  test_query_open_positions_by_model — 2 open + 1 closed for model_A,
      query open → returns 2
GREEN: filter by model_id + is_open=True

RED:  test_query_closed_positions — filter is_open=False → returns closed ones
GREEN: filter by is_open=False

RED:  test_save_and_load_portfolio — PortfolioRow with all fields, save, load → matches
GREEN: PortfolioRow model + repository

RED:  test_update_portfolio — save portfolio, update current_value + lifecycle_state,
      load → reflects updates
GREEN: repository update method

RED:  test_position_manager_loads_from_db — save 2 open positions + 1 portfolio to DB,
      construct PositionManager from DB rows → in-memory state matches DB
GREEN: PositionManager.from_db(session) class method
```

### Phase 7: Score Worker Integration

**File: `tests/test_score_worker_integration.py`**

Integration tests that wire together PositionManager + FeeEngine + LifecycleManager + DB. Use SQLite in-memory. No gRPC — test the score worker's `run_once()` logic with pre-seeded prediction rows.

```
RED:  test_pending_prediction_with_order_scored — seed a PENDING prediction with
      inference_output={action:LONG, trade_pair:BTCUSDT, leverage:0.5},
      seed feed_record with BTCUSDT close=50000 →
      after run_once: prediction=SCORED, order row exists, position row exists (open),
      portfolio row exists, score row has net_pnl
GREEN: wire up score worker with all extensions, call run_once()

RED:  test_pending_prediction_none_order — seed PENDING prediction with
      inference_output={} (model returned None) →
      after run_once: prediction=SCORED, no order row, portfolio still updated
      (mark-to-market)
GREEN: handle empty inference_output as None order

RED:  test_carry_fees_applied — seed open position, set ts to 04:00 UTC →
      after run_once: position carry_fees increased, portfolio total_fees increased
GREEN: carry fee step in run_once

RED:  test_mark_to_market_updates_drawdown — seed portfolio with peak=1.1,
      open position LONG, price drops → after run_once: portfolio current_value < 1.1,
      drawdown_pct > 0
GREEN: mark-to-market step

RED:  test_lifecycle_eliminates_on_drawdown — seed portfolio in CHALLENGE state,
      open position with huge loss → after run_once: lifecycle_state=ELIMINATED
GREEN: lifecycle step in run_once

RED:  test_eliminated_model_excluded_from_leaderboard — seed 2 models, one ELIMINATED →
      leaderboard only contains non-eliminated model
GREEN: filter in leaderboard rebuild
```

### Build Order Summary

```
Phase 1: test_types.py → types.py                          (pure, no deps)
Phase 1: test_tracker.py → tracker.py                      (depends on types)
Phase 2: test_fee_engine.py → fee_engine.py                (pure math)
Phase 3: test_position_manager.py → position_manager.py    (depends on fee_engine)
Phase 4: test_lifecycle_manager.py → lifecycle_manager.py   (pure state machine)
Phase 5: test_scoring.py → scoring.py                       (thin passthrough)
Phase 6: test_trading_repositories.py → tables + repos     (DB layer)
Phase 7: test_score_worker_integration.py → wiring          (everything together)
```

Each phase's tests must be GREEN before starting the next phase. Earlier phases have zero dependencies on later ones — if Phase 3 tests pass, the PositionManager works regardless of whether DB or worker integration exists yet.

---

## 14. Implementation Scope — What Changes vs What's New

### New files to create:
- `challenge/vanta/` — entire package (tracker.py, types.py, scoring.py, examples/)
- `node/db/tables/trading.py` — OrderRow, PositionRow, PortfolioRow
- `node/db/trading_repositories.py` — DB access for new tables
- `node/extensions/position_manager.py` — core order/position/portfolio engine (DB-backed)
- `node/extensions/fee_engine.py` — fee calculations
- `node/extensions/lifecycle_manager.py` — state machine
- `node/api/positions.py` — REST endpoints (stubs)
- `node/config/crunch_config.py` — Vanta-specific types + config
- All test files

### Existing files to modify:
- `coordinator_node/services/feed_reader.py` — strip multi-TF aggregation + microstructure, add `get_latest_candles()`
- `coordinator_node/services/feed_data.py` — remove `_microstructure_loop`
- `coordinator_node/services/predict.py` — add `_encode_tick_per_model()` callable for per-model positions
- `node/workers/score_worker.py` — extend to own PositionManager, run lifecycle checks
- `node/workers/predict_worker.py` — read positions from DB, filter eliminated models, use per-model tick
- `node/db/tables/__init__.py` — register new table models
- `node/db/__init__.py` — export new repositories
- `node/.local.env` — Vanta-specific env vars
- `node/config/crunch_config.py` — scheduled_predictions define tick cycle, scope, and resolution
- `docker-compose.yml` / `Dockerfile` — ensure pandas is available in model containers

### Existing files NOT to modify:
- `coordinator_node/crunch_config.py` — base config classes (we override in config)
- `coordinator_node/services/score.py` — base score service (we extend in score_worker)
- Existing DB tables (inputs, predictions, scores, snapshots, leaderboards, feed_records)
- Feed providers (binance.py) — keep depth/funding fetch capability, just don't call it from feed_data
- `model-runner-client` — no changes, using existing callable arguments API

---

## 15. What NOT to Build

- No multi-timeframe candles (5m/15m/1h) — just 1m
- No orderbook or funding rate data in v1
- No backtesting harness
- No ensemble/multi-model logic
- No complex report worker customization beyond API stubs
- No miner/live-trading layer
- No indicator library
