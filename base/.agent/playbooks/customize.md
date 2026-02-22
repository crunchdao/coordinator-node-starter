# Playbook: Customize Competition

Use this when changing the competition's types, scoring, feeds, emission, or model interface.

## Before you start

1. Read `.agent/context.md` — especially Contract-Based Design and Extension points
2. Read `.agent/policy.md` — emission and scoring changes may require approval
3. Read `node/.agent/context.md` for node-specific edit boundaries
4. Read `challenge/.agent/context.md` for challenge-specific guidance

## Design checklist

Before implementing, confirm these are defined:

1. **Model interface** — tracker class that participants implement
2. **Scoring function** — how predictions are scored against actuals
3. **Feed configuration** — source, subjects, kind, granularity
4. **Prediction schedule** — `prediction_interval_seconds` and `resolve_after_seconds`
5. **Ground truth resolution** — how actuals are derived from feed data
6. **Emission config** — crunch pubkey, provider wallets, tier distribution

If any are missing, ask the user before proceeding.

### Critical: `resolve_after_seconds` must exceed feed granularity

`resolve_after_seconds` defines how long the score-worker waits before looking up ground truth from the feed. If this value is shorter than the feed's data interval (`FEED_GRANULARITY` / `FEED_POLL_SECONDS`), **no ground truth data will exist yet** and all predictions will fail to score.

**Rule:** `resolve_after_seconds` must be **strictly greater** than the feed's effective data interval. Ask the user what value makes sense for their use case — do not guess.

Examples:
- Feed granularity `1s`, poll every `5s` → `resolve_after_seconds` must be > 5
- Feed granularity `1m` → `resolve_after_seconds` must be > 60
- Feed granularity `5m` → `resolve_after_seconds` must be > 300

## Workflow

### 1. Scoring function (do this FIRST)

The scoring function is the most important file in the competition. It defines
what "good" means. **Do not leave it as a stub that returns 0.0** — a pipeline
that scores everything as zero produces meaningless leaderboards silently.

**Steps:**
1. Ask the user: "How should predictions be scored against actuals?" Do not guess.
2. Implement real scoring logic in `challenge/starter_challenge/scoring.py`
3. Wire it in `node/config/callables.env`: `SCORING_FUNCTION=starter_challenge.scoring:score_prediction`
4. Write a unit test that feeds a known prediction + ground truth and asserts a **non-zero** score
5. Ensure `node/runtime_definitions/crunch_config.py` ScoreResult fields match what the function returns

**The scoring function receives:**
- `prediction` — dict with the model's output (matches `InferenceOutput` shape)
- `ground_truth` — dict from `resolve_ground_truth` (see step 3 below)

**It must return:** a dict matching `ScoreResult` — at minimum `{"value": float, "success": bool, "failed_reason": str | None}`

### 2. Ground truth resolution

`resolve_ground_truth` determines what "actually happened" from feed data.
This is the second most important function — if it returns None or zero,
all scores will be zero regardless of model quality.

**Sanity check:** after implementing, verify that the resolver produces
non-zero returns with your configured feed granularity. A 60s horizon with
1m candles can produce 0.0 returns if only one candle falls in the window.

- Default: compares first/last record's close price → returns `entry_price`, `resolved_price`, `return`, `direction_up`
- Override in `CrunchConfig.resolve_ground_truth` for custom logic (VWAP, cross-venue, labels, etc.)

### 3. Types and shapes

Edit `node/runtime_definitions/crunch_config.py`:
- `RawInput` — what the feed produces
- `InferenceInput` — what models receive (can differ from RawInput via transform)
- `InferenceOutput` — what models return
- `ScoreResult` — what scoring produces (must match scoring function output)
- `PredictionScope` — prediction context (subject, horizon, step)

### 4. Multi-metric scoring

- Add/remove metric names in `CrunchConfig.metrics`
- Custom metrics: register via `get_default_registry().register("name", fn)`

### 6. Feeds

Edit `node/.local.env`:
- `FEED_SOURCE` (pyth, binance, etc.)
- `FEED_SUBJECTS` (BTC, ETH, etc.)
- `FEED_KIND` (tick, candle)
- `FEED_GRANULARITY` (1s, 1m, etc.)

### 7. Emission (requires approval)

Edit `CrunchConfig`:
- `crunch_pubkey` — on-chain crunch account
- `compute_provider`, `data_provider` — wallet pubkeys
- `build_emission` — reward distribution logic

### 8. Challenge package

Edit `challenge/starter_challenge/`:
- `tracker.py` — model interface participants implement
- `scoring.py` — local self-eval scoring (should match runtime scoring)
- `examples/` — quickstarter implementations

### 9. Validate

```bash
cd node
make deploy
make verify-e2e
```

### 10. Complete

Produce:
- Summary of what was customized
- Design checklist status (all 5 items confirmed)
- Verification result
- Any assumptions about scoring or emission behavior
