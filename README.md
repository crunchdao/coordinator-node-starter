# coordinator-node

[![PyPI](https://img.shields.io/pypi/v/coordinator-node)](https://pypi.org/project/coordinator-node/)

Runtime engine for Crunch coordinator nodes. Powers the full competition pipeline — from data ingestion through scoring to on-chain emission checkpoints.

```bash
pip install coordinator-node
```

---

## Two ways to use this repo

### 1. Scaffold a new competition (recommended)

Use the Crunch CLI to create a self-contained workspace that pulls `coordinator-node` from PyPI:

```bash
crunch-cli init-workspace my-challenge
cd my-challenge
make deploy
```

This creates:

```
my-challenge/
├── node/          ← docker-compose, config, scripts (uses coordinator-node from PyPI)
├── challenge/     ← participant-facing package (tracker, scoring, examples)
└── Makefile
```

### 2. Develop the engine itself

Clone this repo to work on the `coordinator_node` package directly:

```bash
git clone https://github.com/crunchdao/coordinator-node-starter.git
cd coordinator-node-starter
uv sync
make deploy    # uses local coordinator_node/ via COPY in Dockerfile
```

Changes to `coordinator_node/` are picked up immediately on rebuild.

---

## Architecture

### Pipeline

```
Feed → Input → Prediction → Score → Snapshot → Checkpoint → On-chain
```

### Workers

| Worker | Purpose |
|---|---|
| `feed-data-worker` | Ingests feed data (Pyth, Binance, etc.) via polling + backfill |
| `predict-worker` | Gets latest data → ticks models → collects predictions |
| `score-worker` | Resolves actuals → scores predictions → writes snapshots → rebuilds leaderboard |
| `checkpoint-worker` | Aggregates snapshots → builds EmissionCheckpoint for on-chain submission |
| `report-worker` | FastAPI server: leaderboard, predictions, feeds, snapshots, checkpoints |

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

---

## Configuration

All configuration is via environment variables. Copy the example env file to get started:

```bash
cp .local.env.example .local.env
```

Key variables:

| Variable | Description | Default |
|---|---|---|
| `CRUNCH_ID` | Competition identifier | `starter-challenge` |
| `FEED_SOURCE` | Data source | `pyth` |
| `FEED_SUBJECTS` | Assets to track | `BTC` |
| `SCORING_FUNCTION` | Dotted path to scoring callable | `coordinator_node.extensions.default_callables:default_score_prediction` |
| `CHECKPOINT_INTERVAL_SECONDS` | Seconds between checkpoints | `604800` |
| `MODEL_BASE_CLASSNAME` | Participant model base class | `tracker.TrackerBase` |
| `MODEL_RUNNER_NODE_HOST` | Model orchestrator host | `model-orchestrator` |

---

## Extension Points

Customize competition behavior by setting callable paths in your env:

| Env var | Purpose |
|---|---|
| `SCORING_FUNCTION` | Score a prediction against ground truth |
| `INFERENCE_INPUT_BUILDER` | Transform raw feed data into model input |
| `INFERENCE_OUTPUT_VALIDATOR` | Validate model output shape/values |
| `MODEL_SCORE_AGGREGATOR` | Aggregate per-model scores across predictions |
| `LEADERBOARD_RANKER` | Custom leaderboard ranking strategy |

---

## Contract

All type shapes and behavior are defined in a single `CrunchContract`:

```python
from coordinator_node.contracts import CrunchContract

class CrunchContract(BaseModel):
    raw_input_type: type[BaseModel]
    output_type: type[BaseModel]
    score_type: type[BaseModel]
    scope: PredictionScope
    aggregation: Aggregation

    # Callables
    resolve_ground_truth: Callable
    aggregate_snapshot: Callable
    build_emission: Callable
```

---

## Report API

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

---

## Emission Checkpoints

Checkpoints produce `EmissionCheckpoint` matching the on-chain protocol:

```json
{
    "crunch": "<pubkey>",
    "cruncher_rewards": [{"cruncher_index": 0, "reward_pct": 350000000}],
    "compute_provider_rewards": [],
    "data_provider_rewards": []
}
```

`reward_pct` uses frac64 (1,000,000,000 = 100%).

---

## Database Tables

### Feed layer

| Table | Purpose |
|---|---|
| `feed_records` | Raw data points from external sources. Keyed by `(source, subject, kind, granularity, ts_event)`. Values and metadata stored as JSONB. |
| `feed_ingestion_state` | Tracks the last ingested timestamp per feed scope to enable incremental polling and backfill. |

### Pipeline layer

| Table | Purpose |
|---|---|
| `inputs` | Incoming data events. Status: `RECEIVED → RESOLVED`. Holds raw data, actuals (once known), and scope metadata. |
| `predictions` | One row per model per input. Links to a `scheduled_prediction_config`. Stores inference output, execution time, and resolution timestamp. Status: `PENDING → SCORED / FAILED / ABSENT`. |
| `scores` | One row per scored prediction. Stores the result payload, success flag, and optional failure reason. |
| `snapshots` | Per-model period summaries. Aggregates prediction counts and result metrics over a time window. |
| `checkpoints` | Periodic emission checkpoints. Aggregates snapshots into on-chain reward distributions. Status: `PENDING → SUBMITTED → CLAIMABLE → PAID`. |
| `scheduled_prediction_configs` | Defines when and what to predict — scope template, schedule, and ordering. Seeded at init from `scheduled_prediction_configs.json`. |

### Model layer

| Table | Purpose |
|---|---|
| `models` | Registered participant models. Tracks overall and per-scope scores as JSONB. |
| `leaderboards` | Point-in-time leaderboard snapshots with ranked entries as JSONB. |

---

## Local Development

```bash
# Run tests
uv run pytest tests/ -x -q

# Start all services locally
make deploy

# View logs
make logs

# Tear down
make down
```

---

## Project Structure

```
coordinator-node-starter/
├── coordinator_node/       ← core engine (published to PyPI as coordinator-node)
│   ├── workers/            ← feed, predict, score, checkpoint, report workers
│   ├── services/           ← business logic
│   ├── entities/           ← domain models
│   ├── db/                 ← database tables and init
│   ├── feeds/              ← data source adapters (Pyth, Binance, etc.)
│   ├── schemas/            ← API schemas
│   ├── extensions/         ← default callables
│   ├── config/             ← runtime configuration
│   └── contracts.py        ← competition shape: types, scope, and callable hooks
├── base/                   ← template used by crunch-cli init-workspace
│   ├── node/               ← node template (Dockerfile, docker-compose, config)
│   └── challenge/          ← challenge template (tracker, scoring, examples)
├── tests/                  ← test suite
├── docker-compose.yml      ← local dev compose (uses local coordinator_node/)
├── Dockerfile              ← local dev Dockerfile (COPYs coordinator_node/)
├── pyproject.toml          ← package definition
└── Makefile                ← deploy / down / logs / test
```

---

## Publishing

```bash
uv build
twine upload dist/*
```
