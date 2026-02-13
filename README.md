# crunch-node

Runtime engine for Crunch coordinator nodes. Published as `crunch-node` on PyPI, imported as `coordinator_node`.

```bash
pip install crunch-node
```

## Architecture

### Pipeline

```
Feed → Input → Prediction → Score → Snapshot → Checkpoint → On-chain
```

**Workers:**

| Worker | Purpose |
|---|---|
| `feed-data-worker` | Ingests feed data (Pyth, Binance, etc.) via WebSocket + backfill |
| `predict-worker` | Event-driven: gets data → ticks models → collects predictions |
| `score-worker` | Resolves actuals → scores predictions → writes snapshots → rebuilds leaderboard |
| `checkpoint-worker` | Aggregates snapshots → builds EmissionCheckpoint for on-chain submission |
| `report-worker` | FastAPI: leaderboard, predictions, feeds, snapshots, checkpoints, emissions |

### Contract

All type shapes and behavior are defined in a single `CrunchContract`:

```python
from coordinator_node.contracts import CrunchContract

class CrunchContract(BaseModel):
    raw_input_type: type[BaseModel] = RawInput
    output_type: type[BaseModel] = InferenceOutput
    score_type: type[BaseModel] = ScoreResult
    scope: PredictionScope = PredictionScope()
    aggregation: Aggregation = Aggregation()

    # Callables
    resolve_ground_truth: Callable = default_resolve_ground_truth
    aggregate_snapshot: Callable = default_aggregate_snapshot
    build_emission: Callable = default_build_emission
```

### Feed Dimensions

| Dimension | Example | Env var |
|---|---|---|
| `source` | pyth, binance | `FEED_SOURCE` |
| `subject` | BTC, ETH | `FEED_SUBJECTS` |
| `kind` | tick, candle | `FEED_KIND` |
| `granularity` | 1s, 1m | `FEED_GRANULARITY` |

### Status Lifecycles

```
Input:       RECEIVED → RESOLVED
Prediction:  PENDING → SCORED / FAILED / ABSENT
Checkpoint:  PENDING → SUBMITTED → CLAIMABLE → PAID
```

### Emission Checkpoints

Checkpoints produce `EmissionCheckpoint` matching the on-chain protocol:

```python
{
    "crunch": "<pubkey>",
    "cruncher_rewards": [{"cruncher_index": 0, "reward_pct": 350_000_000}, ...],
    "compute_provider_rewards": [...],
    "data_provider_rewards": [...],
}
```

`reward_pct` uses frac64 (1,000,000,000 = 100%).

### Report API

| Endpoint | Description |
|---|---|
| `GET /reports/leaderboard` | Current leaderboard |
| `GET /reports/models` | Registered models |
| `GET /reports/predictions` | Prediction history |
| `GET /reports/feeds` | Active feed subscriptions |
| `GET /reports/snapshots` | Per-model period summaries |
| `GET /reports/checkpoints` | Checkpoint history |
| `GET /reports/checkpoints/{id}/emission` | Raw emission (frac64) |
| `GET /reports/checkpoints/{id}/emission/cli-format` | CLI JSON format |
| `GET /reports/emissions/latest` | Latest emission |
| `POST /reports/checkpoints/{id}/confirm` | Record tx_hash |
| `PATCH /reports/checkpoints/{id}/status` | Advance status |

## Scaffolding

Use `crunch-cli init-workspace <name>` to create a new competition workspace from the `base/` template.

## Development

```bash
uv run pytest tests/ -q
```
