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

## ⚠️ Starter placeholder values

The tracker, scoring function, and examples ship with placeholder values
(subject="BTC", horizon_seconds=60, `{"value": float}`, etc.) that make
the scaffold run out of the box. **These are not real defaults.**

When customizing for a new competition:
- Do NOT copy the starter `predict()` signature as-is — ask the user what
  arguments and return shape their competition needs
- Do NOT keep `{"value": float}` as InferenceOutput unless confirmed — it
  must match what the scoring function reads and what models return
- Do NOT keep the example models unchanged — update them to use the real
  prediction shape and signal logic for the new competition
- The scoring stub (`return 0.0`) must be replaced with real logic FIRST

See `../.agent/playbooks/customize.md` for the full placeholder table.

## Development guidance

- Keep participant-facing challenge logic in this package
- Keep runtime contracts and deployment config in `../node/`
- The scoring function in `scoring.py` is used for both local self-eval and backtest. The runtime scoring callable is configured separately in `crunch_config.py`
- When publishing, set `COORDINATOR_URL` in `config.py` to the actual coordinator address
- `config.py` is auto-generated — only edit `COORDINATOR_URL` for publishing

## Tests

Run from workspace root: `make test` (or `cd challenge && uv run --extra dev python -m pytest tests/ -v`).

### Test files

| File | Purpose |
|---|---|
| `tests/test_tracker.py` | TrackerBase per-subject data isolation, `_default` fallback, edge cases |
| `tests/test_scoring.py` | Scoring contract (shape/types) + behavioral stub detection |
| `tests/test_examples.py` | All example trackers: contract compliance, boundaries, multi-subject |

### Scoring stub detection pattern

`test_scoring.py` has two test classes:

- **`TestScoringContract`** — shape/type checks that pass for ANY valid implementation (always green).
- **`TestScoringBehavior`** — behavioral tests marked `xfail(strict=True)` that **intentionally fail against the 0.0 stub**. These are TDD targets:
  - `test_correct_prediction_scores_positive` — bullish prediction + price up = positive score
  - `test_wrong_prediction_scores_negative` — bullish prediction + price down = negative score
  - `test_different_inputs_produce_different_scores` — different ground truths ≠ same score

**When you implement real scoring:**
1. Remove the `@pytest.mark.xfail(...)` decorators from these tests
2. Adjust the assertions to match your scoring logic
3. Add more tests for your specific scoring edge cases

If you implement scoring but forget to remove the xfail markers, pytest will
report XPASS (unexpected pass) as a **failure** — this is intentional. It forces
you to update the tests to match your implementation.

## Validation

Quick validation is that the backtest should work from the Challenge repository.

```bash
# Unit tests (no Docker)
make test

# Or from workspace root
cd .. && make test
```

E2E validation from the node workspace:

```bash
cd ../node
make deploy
make verify-e2e
```
And verify that models are running.
