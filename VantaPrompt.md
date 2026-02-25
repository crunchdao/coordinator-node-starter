Build: Vanta Coordinator — Order-Based Crypto Trading Competition

 Build a Crunch coordinator (https://github.com/crunchdao/coordinator-node-starter) that replicates Vanta Network (https://github.com/taoshidev/vanta-network/blob/main/docs/miner.md) miner game dynamics as a competition. Models act as traders — submitting leveraged
 LONG/SHORT/FLAT orders on live Binance crypto data. The coordinator tracks positions, applies fees, scores PnL, enforces lifecycle rules, and ranks models on a leaderboard.

 Use the crunch-coordinate skill to scaffold the coordinator workspace, then customize it with the spec below.

 ────────────────────────────────────────────────────────────────────────────────

 Design Principles

 1. Minimal core, extensible later. Only build what's specified. No backtesting harness, no miner layer, no ensemble logic.
 2. Everything typed. Dataclasses for domain objects. Pydantic for framework contracts. Type hints on every function signature.
 3. Stateful position tracking. The scoring function is a thin passthrough. All PnL computation happens in the PositionManager extension, which maintains per-model portfolio state across prediction cycles.
 4. Models can do nothing. trade() returns Order | None. None means no action this cycle — the model still gets a portfolio snapshot (mark-to-market update) but no order is executed.
 5. All constants from env vars. Every Vanta parameter (leverage limits, fee rates, lifecycle thresholds) is read from environment variables with sensible defaults. Nothing hardcoded in logic.
 6. Tests for every extension. Position rules, fee math, lifecycle transitions — all covered.

 ────────────────────────────────────────────────────────────────────────────────

 Architecture

 ```
   challenge/                          # pip-installable participant package
     vanta/
       __init__.py
       types.py                        # Order, Position, Candle, MarketData dataclasses
       tracker.py                      # TrackerBase with trade() interface
       scoring.py                      # score_prediction() + risk metric functions
       config.py                       # package metadata

   node/                               # coordinator infrastructure
     config/
       crunch_config.py                # CrunchConfig (types, predictions, callables, behavior)
       callables.env                   # scoring function callable path
     extensions/
       __init__.py
       position_manager.py             # Order → Position → Portfolio → Snapshot
       fee_engine.py                   # Carry (scheduled), spread, slippage
       lifecycle_manager.py            # CHALLENGE → MAINCOMP → PROBATION → ELIMINATED
     api/
       __init__.py
       positions.py                    # Custom REST endpoints for position/lifecycle state
     deployment/
       model-orchestrator-local/
         config/
           starter-submission/         # example model
           models.dev.yml
         data/submissions/
           starter-submission/         # deployed copy
     scripts/
       verify_e2e.py
     docker-compose.yml
     Dockerfile
     Makefile
     .local.env

   tests/                              # pytest suite (NOT inside node/ or challenge/)
     __init__.py
     test_position_manager.py
     test_fee_engine.py
     test_lifecycle_manager.py
     test_scoring.py
     test_tracker.py

   Makefile                            # top-level: deploy, test, logs
   README.md
 ```

 ────────────────────────────────────────────────────────────────────────────────

 1. Model Interface — challenge/vanta/tracker.py

 ```python
   class TrackerBase:
       def tick(self, data: dict) -> None: ...
       def trade(self) -> Order | None: ...
       def predict(self, subject, resolve_horizon_seconds, step_seconds) -> dict | None: ...  # adapter, do NOT override
 ```

 - tick(data) receives per-symbol market data (1m/5m/15m/1h candles, optional orderbook + funding). Called every feed update. Store data keyed by data["symbol"].
 - trade() is the method participants implement. Returns Order("LONG", "BTCUSDT", leverage=0.5) or None. Has access to self.positions (dict of current open positions, updated by coordinator) and self._latest_data / self._history.
 - predict() is the framework adapter. Calls trade(), converts Order to dict, passes None through unchanged. Participants never override this.

 ────────────────────────────────────────────────────────────────────────────────

 2. Typed Contracts — challenge/vanta/types.py

 All domain types as dataclasses with validation in __post_init__:

 ```python
   SUPPORTED_PAIRS: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"]
   VALID_ACTIONS: set[str] = {"LONG", "SHORT", "FLAT"}

   @dataclass
   class Order:
       action: str           # LONG, SHORT, FLAT
       trade_pair: str       # must be in SUPPORTED_PAIRS
       leverage: float = 0.0 # 0.001–2.5 for crypto; ignored for FLAT
       # __post_init__ validates action, trade_pair, leverage range

   @dataclass
   class Position:
       direction: str        # LONG, SHORT
       leverage: float
       entry_price: float
       unrealized_pnl: float = 0.0
       fees_accrued: float = 0.0

   @dataclass
   class Candle:
       open: float
       high: float
       low: float
       close: float
       volume: float
       timestamp: int = 0

   @dataclass
   class MarketData:
       symbol: str = "BTCUSDT"
       asof_ts: int = 0
       candles_1m: list[dict] = field(default_factory=list)
       candles_5m: list[dict] = field(default_factory=list)
       candles_15m: list[dict] = field(default_factory=list)
       candles_1h: list[dict] = field(default_factory=list)
       orderbook: dict | None = None
       funding: dict | None = None
 ```

 ────────────────────────────────────────────────────────────────────────────────

 3. Position Manager — node/extensions/position_manager.py

 This is the core engine. Maintains a PortfolioState per model with open_positions and closed_positions.

 ### Data structures (all dataclasses, all typed):

 - Order — action, trade_pair, leverage, timestamp, price, spread_fee, slippage_fee, accepted, rejected_reason
 - Position — trade_pair, direction, leverage, entry_price, entry_ts, max_seen_leverage, fees (carry/spread/slippage), realized_pnl, is_open, close_ts/price. Methods: unrealized_pnl(price), net_pnl(price), total_fees.
 - PortfolioState — model_id, open_positions dict, closed_positions list, peak_value, current_value, last_order_ts dict, registration_ts.

 ### PositionManager class:

 Constructor takes: supported_pairs, position_leverage_min, position_leverage_max, portfolio_leverage_max, order_cooldown_seconds, spread_fee_rate, slippage_bps. All from env vars.

 process_order(model_id, order_dict, current_prices, ts) → dict:
 1. If order_dict is None → skip to snapshot (no order executed, model chose inaction)
 2. Validate: action ∈ {LONG, SHORT, FLAT}, pair is supported, cooldown not active (10s per pair), leverage ≥ min
 3. Execute:
     - FLAT → close position, book realized PnL
     - New position → create with clamped leverage (per-position max, portfolio max)
     - Same direction → increase leverage, weighted-average entry price
     - Opposite direction, partial → reduce leverage
     - Opposite direction, full+ → close existing (book PnL), open remainder in opposite direction
 4. Apply spread fee (spread_rate × order_leverage) and slippage fee (slippage_bps/10000 × order_leverage) at order time
 5. Compute and return snapshot dict: portfolio_value, unrealized_pnl, realized_pnl, total_fees, gross_pnl, net_pnl, drawdown_pct, portfolio_leverage, open_positions count, order_accepted, order_rejected_reason

 get_positions_for_model(model_id) → dict[str, dict]: simplified position view for passing to model's self.positions.

 ### Position rules (Vanta parity):

 - Uni-directional: positions can't flip. Excess opposite leverage closes + reopens.
 - Max 1 open position per pair per model.
 - 10-second cooldown between orders on same pair.
 - Leverage below minimum → rejected (not clamped). Above maximum → clamped (not rejected).
 - Portfolio leverage (sum of all open) → clamped (not rejected).

 ────────────────────────────────────────────────────────────────────────────────

 4. Fee Engine — node/extensions/fee_engine.py

 Three fee types:

 ┌──────────┬───────────────┬────────────────────────────────────┬────────────────────────────────────────────────────┐
 │ Fee      │ Rate          │ When                               │ Formula                                            │
 ├──────────┼───────────────┼────────────────────────────────────┼────────────────────────────────────────────────────┤
 │ Spread   │ 0.1%          │ Each order                         │ SPREAD_FEE_RATE × order_leverage                   │
 ├──────────┼───────────────┼────────────────────────────────────┼────────────────────────────────────────────────────┤
 │ Slippage │ 3 bps         │ Each order                         │ (SLIPPAGE_BPS / 10000) × order_leverage            │
 ├──────────┼───────────────┼────────────────────────────────────┼────────────────────────────────────────────────────┤
 │ Carry    │ 10.95% annual │ Every 8h (04:00, 12:00, 20:00 UTC) │ (daily_rate × max_seen_leverage) / periods_per_day │
 └──────────┴───────────────┴────────────────────────────────────┴────────────────────────────────────────────────────┘

 Key: carry uses max leverage ever seen on that position, not current leverage. Tracked per model_id:trade_pair. Applied once per carry hour (deduplicated).

 ### FeeEngine class:

 - compute_spread_fee(leverage) → float
 - compute_slippage_fee(leverage) → float
 - should_apply_carry(model_id, trade_pair, ts) → bool
 - apply_carry_fees(portfolio, ts) → float (total carry applied this cycle)

 All rates configurable via env vars: CARRY_ANNUAL_RATE, CARRY_INTERVAL_HOURS, CARRY_TIMES_UTC, SPREAD_FEE_RATE, SLIPPAGE_BPS.

 ────────────────────────────────────────────────────────────────────────────────

 5. Lifecycle Manager — node/extensions/lifecycle_manager.py

 State machine per model:

 ```
   Register → IMMUNITY (4h) → CHALLENGE (90d) → MAINCOMP → (optional) PROBATION (60d) → ELIMINATED
 ```

 ┌────────────┬─────────────────────────┬───────────┬───────────────────────────────────────────────────────────────────────────┐
 │ State      │ Entry                   │ Duration  │ Exit                                                                      │
 ├────────────┼─────────────────────────┼───────────┼───────────────────────────────────────────────────────────────────────────┤
 │ IMMUNITY   │ Registration            │ 4 hours   │ Auto → CHALLENGE                                                          │
 ├────────────┼─────────────────────────┼───────────┼───────────────────────────────────────────────────────────────────────────┤
 │ CHALLENGE  │ After immunity          │ 90 days   │ Pass: 61+ trading days, DD < 10%, rank ≤ 25 → MAINCOMP. Fail → ELIMINATED │
 ├────────────┼─────────────────────────┼───────────┼───────────────────────────────────────────────────────────────────────────┤
 │ MAINCOMP   │ Pass challenge          │ Ongoing   │ DD > 10% → ELIMINATED. Rank drops below 25 → PROBATION                    │
 ├────────────┼─────────────────────────┼───────────┼───────────────────────────────────────────────────────────────────────────┤
 │ PROBATION  │ Demoted from MAINCOMP   │ 60 days   │ Recover to top 25 → MAINCOMP. Timeout → ELIMINATED                        │
 ├────────────┼─────────────────────────┼───────────┼───────────────────────────────────────────────────────────────────────────┤
 │ ELIMINATED │ Any elimination trigger │ Permanent │ Blacklisted, cannot re-register                                           │
 └────────────┴─────────────────────────┴───────────┴───────────────────────────────────────────────────────────────────────────┘

 Probation/rank rules only activate when MIN_MODELS_FOR_PROBATION (default 10) models are competing.

 ### LifecycleManager class:

 - register_model(model_id, ts) → ModelLifecycle
 - update(model_id, drawdown_pct, rank, trading_days, total_models, ts) → ModelLifecycle
 - is_in_immunity(model_id, ts) → bool
 - get_active_models() → list[ModelLifecycle]
 - get_summary() → dict

 ### ModelLifecycle dataclass:

 - model_id, state (enum), registration_ts, challenge_start_ts, maincomp_start_ts, probation_start_ts, elimination_ts, elimination_reason, trading_days, current_rank, max_drawdown_pct

 All thresholds from env vars: CHALLENGE_PERIOD_DAYS, CHALLENGE_MIN_TRADING_DAYS, MAX_DRAWDOWN_PCT, PROBATION_DAYS, PROBATION_RANK_CUTOFF, MIN_MODELS_FOR_PROBATION, IMMUNITY_HOURS.

 ────────────────────────────────────────────────────────────────────────────────

 6. Scoring — challenge/vanta/scoring.py

 ### score_prediction(prediction, ground_truth) → dict

 This is a thin passthrough. The PositionManager has already computed the portfolio snapshot and injected it into prediction["portfolio_snapshot"]. This function extracts it and returns a ScoreResult-shaped dict with "value": net_pnl.

 The ground_truth parameter is not used by this function (position manager already marked to market).

 ### Risk metrics (secondary, all at 0% weight but computed):

 All take list[float] of daily returns:

 - avg_daily_pnl(daily_returns) — recency-weighted mean (aggressive: half-life 15d)
 - calmar_ratio(daily_returns, max_drawdown) — annualized return / max DD, minus risk-free rate
 - sharpe_ratio(daily_returns) — annualized excess return / vol (1% vol floor)
 - omega_ratio(daily_returns) — Σ positive / |Σ negative| (1% floor)
 - sortino_ratio(daily_returns) — annualized excess return / downside vol (1% floor)
 - t_statistic(daily_returns) — mean / (std / √n)

 ### Recency weighting:

 - Aggressive (for PnL): half-life 15 days → 10d=40%, 30d=70%, 70d=87%
 - Standard (for ratios): half-life 25 days → 10d=25%, 30d=50%, 70d=75%

 RISK_FREE_RATE from env var (default 0.05 = 5% T-bill).

 ────────────────────────────────────────────────────────────────────────────────

 7. CrunchConfig — node/config/crunch_config.py

 Pydantic models for the framework contracts:

 - RawInput / InferenceInput: symbol, asof_ts, candles_1m/5m/15m/1h, orderbook, funding
 - InferenceOutput: action (LONG/SHORT/FLAT), trade_pair, leverage
 - ScoreResult: value, portfolio_value, unrealized_pnl, realized_pnl, total_fees, gross_pnl, net_pnl, drawdown_pct, portfolio_leverage, open_positions, order_accepted, order_rejected_reason, success, failed_reason
 - PredictionScope: subject, step_seconds=15 (ge=1). resolve_horizon_seconds is injected from ScheduledPrediction.resolve_horizon_seconds
 - Aggregation: three windows as a **dict** (not a list) — `{"pnl_24h": AggregationWindow(hours=24), "pnl_72h": AggregationWindow(hours=72), "pnl_7d": AggregationWindow(hours=168)}`. AggregationWindow only accepts `hours` (no `name`, no `seconds`; extra="forbid"). Ranking by `ranking_key` + `ranking_direction="desc"` (NOT `ranking_order`).
 - Callables: resolve_ground_truth, aggregate_snapshot, build_emission, compute_metrics

 ### resolve_ground_truth:

 Receives `list[FeedRecord]` (dataclass with `.subject`, `.values`, `.ts_event` attributes — NOT `list[dict]`). Returns latest price from feed records. For order-based scoring, ground truth is just the current market price for mark-to-market.

 ### build_emission:

 Tier-based: 1st=35%, 2nd-5th=10% each, 6th-10th=5% each. Unclaimed redistributed equally.

 ────────────────────────────────────────────────────────────────────────────────

 8. API Endpoints — node/api/positions.py

 FastAPI router at /positions, auto-mounted by report worker:

 ┌──────────────────────────────────────┬─────────────────────────────────────────────────────────────┐
 │ Endpoint                             │ Description                                                 │
 ├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
 │ GET /positions/rules                 │ Full competition rules (leverage, fees, lifecycle, scoring) │
 ├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
 │ GET /positions/pairs                 │ Supported pairs and limits                                  │
 ├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
 │ GET /positions/models                │ All models with position summaries                          │
 ├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
 │ GET /positions/models/{id}           │ Detailed model view                                         │
 ├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
 │ GET /positions/models/{id}/positions │ Open and closed positions                                   │
 ├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
 │ GET /positions/models/{id}/orders    │ Paginated order history                                     │
 ├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
 │ GET /positions/models/{id}/lifecycle │ Lifecycle state                                             │
 ├──────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
 │ GET /positions/lifecycle/summary     │ Models grouped by state                                     │
 └──────────────────────────────────────┴─────────────────────────────────────────────────────────────┘

 These can start as stub endpoints that return the correct shape. Integration with coordinator DB is a future extension.

 ────────────────────────────────────────────────────────────────────────────────

 9. Example Models

 ### Starter Submission (deployed)

 Simple SMA crossover on BTCUSDT. Goes LONG when fast SMA > slow SMA, SHORT when reversed, FLAT when signal is weak. Returns None when there's insufficient data or the signal is in the dead zone.

 ### 3 example strategies in challenge/vanta/examples/:

 1. Trend Following — dual SMA crossover on BTCUSDT
 2. Mean Reversion — Bollinger Band reversion on ETHUSDT
 3. Volatility Regime — monitors vol across pairs, trades low-vol breakouts

 Each must demonstrate:
 - Returning Order(...) for a trade
 - Returning None for no action
 - Using self.positions to check current state before trading
 - Keying state by symbol for multi-pair support

 ────────────────────────────────────────────────────────────────────────────────

 10. Configuration — node/.local.env

 Every Vanta parameter as a named env var. Group by concern:

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
   RISK_FREE_RATE=0.05
   SCORING_FUNCTION=vanta.scoring:score_prediction
 ```

 ────────────────────────────────────────────────────────────────────────────────

 11. Tests — tests/

 ### test_position_manager.py

 - Open long/short, verify direction + leverage + entry price
 - None order → snapshot computed, no position opened
 - Leverage below minimum → rejected
 - Leverage above maximum → clamped (not rejected)
 - Portfolio leverage cap → clamped
 - Same direction → increases leverage, weighted avg entry
 - Opposite direction partial → reduces leverage
 - Opposite direction exceeds → close + reopen remainder
 - FLAT → closes position, books realized PnL
 - FLAT on no position → rejected
 - Cooldown enforced (same pair), not enforced (different pair)
 - Unsupported pair → rejected
 - Invalid action → rejected
 - No price available → rejected
 - Long profit/loss with price movement
 - Short profit/loss with price movement
 - Drawdown tracking (peak → drop)
 - Multi-model independence
 - Fees applied at order time (spread + slippage)

 ### test_fee_engine.py

 - Spread fee = rate × leverage
 - Slippage fee = bps × leverage
 - Carry applied at correct UTC hours (04, 12, 20)
 - Carry NOT applied at other hours
 - Carry uses max_seen_leverage, not current
 - Carry applied once per hour (deduplicated)
 - Carry reset when position closed

 ### test_lifecycle_manager.py

 - New model starts in CHALLENGE
 - Immunity period blocks elimination
 - Drawdown > 10% → ELIMINATED (from any state except immunity)
 - Challenge pass → MAINCOMP (enough days, good rank, low DD)
 - Challenge fail: insufficient trading days → ELIMINATED
 - Challenge fail: bad rank → ELIMINATED
 - MAINCOMP rank drop → PROBATION (only when ≥ MIN_MODELS)
 - PROBATION recovery → MAINCOMP
 - PROBATION timeout → ELIMINATED
 - Eliminated model cannot re-register
 - get_active_models excludes eliminated
 - get_summary groups by state

 ### test_scoring.py

 - score_prediction extracts net_pnl as value
 - Empty snapshot → value = 0.0
 - Recency weights sum to 1.0
 - Recent days weighted more than old days
 - avg_daily_pnl positive/negative/empty
 - calmar_ratio with zero drawdown → 0.0
 - sharpe_ratio volatility floor prevents division by zero
 - omega_ratio mixed positive/negative
 - sortino_ratio with no downside → uses floor
 - t_statistic near-zero mean

 ### test_tracker.py

 - TrackerBase.trade() raises NotImplementedError
 - Subclass returning Order → predict() returns dict
 - Subclass returning None → predict() returns None
 - tick() stores data per symbol
 - positions dict accessible from trade()
 - Order validation in types.py (__post_init__)

 ────────────────────────────────────────────────────────────────────────────────

 What NOT to Build

 - No miner/live-trading layer (future extension)
 - No indicator library (future extension)
 - No ensemble/multi-model logic (future extension)
 - No custom metrics registry integration (use defaults)
 - No position state persistence to DB (in-memory for now, DB integration is future)
 - No complex report worker customization beyond the API stubs

