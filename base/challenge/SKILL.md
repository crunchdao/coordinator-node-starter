---
name: starter-challenge-challenge
summary: Agent instructions for implementing challenge logic.
---

# Challenge skill - challenge

## Primary implementation files

- `starter_challenge/tracker.py` — model interface (participants implement this)
- `starter_challenge/scoring.py` — scoring function for local self-eval
- `starter_challenge/backtest.py` — backtest harness for local model evaluation
- `starter_challenge/config.py` — baked-in coordinator URL and feed defaults
- `starter_challenge/examples/` — quickstarter implementations

## Backtest harness

The backtest module provides:

- `BacktestClient` — fetches parquet data from coordinator, caches locally
- `BacktestRunner` — replays historical data through models (tick → predict → score)
- `BacktestResult` — notebook-friendly output (DataFrames, rolling window metrics)

Key design decisions:
- Coordinator URL and feed dimensions are baked into `config.py` at package build time
- Data auto-pulls on first backtest run (transparent caching)
- Model code is identical between backtest and production
- Scoring and metrics match production exactly

## Runtime contract (node-private)

- `../node/runtime_definitions/contracts.py` — CrunchContract defining types, scoring, emission

## Development guidance

- Keep participant-facing challenge logic in this package.
- Keep runtime contracts and deployment config in `../node/`.
- The scoring function in `scoring.py` is used for both local self-eval and backtest.
  The runtime scoring callable is configured in `contracts.py`.
- When publishing, set `COORDINATOR_URL` in `config.py` to the actual coordinator address.

## Validate from node workspace

```bash
cd ../node
make verify-e2e
```
