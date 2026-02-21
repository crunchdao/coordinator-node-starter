# Challenge Context — starter-challenge

## What this is

Participant-facing Python package. Contains the model interface, scoring for local self-eval, backtest harness, and quickstarter examples.

## Primary implementation files

| File | Purpose |
|---|---|
| `starter_challenge/tracker.py` | Model interface — participants implement this |
| `starter_challenge/scoring.py` | Scoring function for local self-eval |
| `starter_challenge/backtest.py` | Backtest harness for local model evaluation |
| `starter_challenge/config.py` | Baked-in coordinator URL and feed defaults |
| `starter_challenge/examples/` | Quickstarter implementations |

## Backtest harness

The backtest module provides:

- **BacktestClient** — fetches parquet data from coordinator, caches locally
- **BacktestRunner** — replays historical data through models (tick → predict → score)
- **BacktestResult** — notebook-friendly output (DataFrames, rolling window metrics + multi-metric enrichment)

Key questions that need to be clarified if extending this: 
- The Base Model interface in `tracker.py`. This includes the model input and output objects/
- Where backtest data is located
- If there is live data and from where it would come
- What the scoring function is.
- How many examples/quickstarter or benchmark models should be created.


Key design decisions:

- Coordinator URL and feed dimensions are baked into `config.py` at package build time
- Data auto-pulls on first backtest run (transparent caching)
- Scoring and rolling window metrics match production exactly
- Multi-metric enrichment is computed using the same metrics registry as the coordinator
- `result.metrics` returns both rolling windows and portfolio-level metrics in a single dict

## Cross-references

- Runtime contract (node-private): `../node/runtime_definitions/crunch_config.py` — CrunchConfig defining types, scoring, emission

## Development guidance

- Keep participant-facing challenge logic in this package
- Keep runtime contracts and deployment config in `../node/`
- The scoring function in `scoring.py` is used for both local self-eval and backtest. The runtime scoring callable is configured separately in `crunch_config.py`
- When publishing, set `COORDINATOR_URL` in `config.py` to the actual coordinator address
- `config.py` is auto-generated — only edit `COORDINATOR_URL` for publishing

## Validation

Quick validation is that the backtest should work from the Challenge repository. 


E2E validation from the node workspace:

```bash
cd ../node
make verify-e2e
```
And verify that models are running.
