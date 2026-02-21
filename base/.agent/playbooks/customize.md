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
4. **Ground truth resolution** — how actuals are derived from feed data
5. **Emission config** — crunch pubkey, provider wallets, tier distribution

If any are missing, ask the user before proceeding.

## Workflow

### 1. Types and shapes

Edit `node/runtime_definitions/crunch_config.py`:
- `RawInput` — what the feed produces
- `InferenceInput` — what models receive (can differ from RawInput via transform)
- `InferenceOutput` — what models return
- `ScoreResult` — what scoring produces
- `PredictionScope` — prediction context (subject, horizon, step)

### 2. Scoring

- Default scoring callable: set in `node/config/callables.env` (`SCORING_FUNCTION=...`)
- Or override directly in `CrunchConfig.resolve_ground_truth`, `CrunchConfig.aggregate_snapshot`
- Multi-metric: add/remove metric names in `CrunchConfig.metrics`
- Custom metrics: register via `get_default_registry().register("name", fn)`

### 3. Feeds

Edit `node/.local.env`:
- `FEED_SOURCE` (pyth, binance, etc.)
- `FEED_SUBJECTS` (BTC, ETH, etc.)
- `FEED_KIND` (tick, candle)
- `FEED_GRANULARITY` (1s, 1m, etc.)

### 4. Emission (requires approval)

Edit `CrunchConfig`:
- `crunch_pubkey` — on-chain crunch account
- `compute_provider`, `data_provider` — wallet pubkeys
- `build_emission` — reward distribution logic

### 5. Challenge package

Edit `challenge/starter_challenge/`:
- `tracker.py` — model interface participants implement
- `scoring.py` — local self-eval scoring (should match runtime scoring)
- `examples/` — quickstarter implementations

### 6. Validate

```bash
cd node
make deploy
make verify-e2e
```

### 7. Complete

Produce:
- Summary of what was customized
- Design checklist status (all 5 items confirmed)
- Verification result
- Any assumptions about scoring or emission behavior
