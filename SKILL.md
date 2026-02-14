---
name: coordinator-node-starter
description: Use when creating or customizing a Crunch coordinator node from this template repository and defining competition contracts before implementation.
---

# Coordinator Node Starter

Use this repository as the **base template source** for new Crunch coordinator nodes.

- This repo provides: `coordinator_core/` + `node_template/`
- You create: `crunch-<name>` (public package) and `crunch-node-<name>` (private runnable node)
- The coordinator agent should guide users through required design decisions before code changes

---

## Template Usage Model (Required)

When the user wants a new Crunch, use the CLI-first scaffold flow:

1. Create an upfront answers file (JSON/YAML) for deterministic setup decisions.
2. Run preflight to halt on busy local ports.
3. Run `coordinator init` (with `--answers` and optional `--spec`).
4. Implement challenge logic in generated `crunch-<name>`.
5. Run generated node verification flow in `crunch-node-<name>`.

Reference: `docs/flow.md`.

This repository is the **template and contract baseline**, not the long-term identity of a specific Crunch.

---

## Required Crunch Definition (Must Be Explicit)

Before implementation, the agent must help the user define and validate these six points:

1. **Define Model Interface**
2. **Define inference input**
3. **Define inference output**
4. **Define scoring function**
5. **Define ModelScore**
6. **Define checkpoint interval**

If any point is missing, stop implementation and ask follow-up questions.

---

## Competition Design Checklist (Conversation Flow)

### 0. Project Name (ask first)
Ask:
> What should we call this Crunch? (used for `crunch-<name>` and `crunch-node-<name>`)

### 1. Define Model Interface
Ask:
> What methods must participant models implement, and what are runtime constraints (timeout, state, allowed libs)?

Output required:
- base class contract in `crunch-<name>`
- model runner `base_classname` to configure in node runtime

### 2. Define inference input
Ask:
> What raw data enters the system, and what transformed payload is sent to models?

Output required:
- input builder callable signature: `build_input(raw_input) -> dict`
- optional schema artifact in `crunch-<name>`

### 3. Define inference output
Ask:
> What should `predict` return (shape, length, validation rules, failure rules)?

Output required:
- output contract in `crunch-<name>`
- validator callable signature: `validate_output(inference_output) -> dict`

### 4. Define scoring function
Ask:
> How are predictions scored against ground truth, and how are invalid outputs handled?

Output required:
- scoring callable signature: `score_prediction(prediction, ground_truth) -> {value, success, failed_reason}`
- callable path in node config: `SCORING_FUNCTION=...`

### 5. Define ModelScore
Ask:
> How should per-model performance be aggregated and represented?

Output required:
- model-score aggregator callable signature: `aggregate_model_scores(scored_predictions, models) -> list[dict]`
- JSON-serializable score payload strategy (`score_payload_jsonb`)

### 6. Define checkpoint interval
Ask:
> What scoring/predict loop interval do you want for this Crunch node?

Output required:
- `CHECKPOINT_INTERVAL_SECONDS` value for `crunch-node-<name>`
- rationale for cadence vs cost/latency

### 7. Configure multi-metric scoring (optional)
Ask:
> Which portfolio-level metrics should the leaderboard compute? (default: ic, ic_sharpe, hit_rate, max_drawdown, model_correlation — set `metrics=[]` to disable)

Output required:
- `CrunchConfig.metrics` list in contract
- Optional: custom metric registrations
- Optional: `ranking_key` set to a metric name (e.g. `ic_sharpe`)

### 8. Configure ensemble (optional)
Ask:
> Should this competition combine model predictions into ensemble meta-models? (default: off)

Output required:
- `CrunchConfig.ensembles` list in contract (empty = off)
- Strategy choice (`inverse_variance` or `equal_weight`)
- Optional: model filter (`top_n`, `min_metric`)

---

## Where To Implement In This Structure

### Stable core contracts
- `coordinator_core/infrastructure/db/db_tables.py`
- `coordinator_core/entities/*`
- `coordinator_core/services/interfaces/*`

### Default runtime template
- `coordinator_node/workers/*`
- `coordinator_node/services/*`
- `coordinator_node/db/*`
- `coordinator_node/config/extensions.py`
- `coordinator_node/config/runtime.py`
- `coordinator_node/extensions/default_callables.py`

Current operational defaults in this template:
- `predict-worker` and `score-worker` configure INFO logging and emit lifecycle/idle logs.
- `ScoreService` attempts repository rollbacks on loop exceptions (where `rollback()` is available).

### Backfill & backtest
- `coordinator_node/services/parquet_sink.py` — Hive-partitioned parquet writer for backfill data
- `coordinator_node/services/backfill.py` — paginated backfill with job tracking and resume
- `coordinator_node/db/backfill_jobs.py` — backfill job persistence (pending → running → completed/failed)
- `coordinator_node/db/tables/backfill.py` — backfill_jobs table definition
- Report worker endpoints: `/reports/backfill/*` (management) + `/data/backfill/*` (parquet serving)

### Challenge package backtest
- `base/challenge/starter_challenge/backtest.py` — BacktestClient, BacktestRunner, BacktestResult
- `base/challenge/starter_challenge/config.py` — baked-in coordinator URL and feed defaults
- Auto-pulls data from coordinator on first run, caches locally
- Same tick/predict/score loop as production

### Multi-metric scoring
- `coordinator_node/metrics/registry.py` — MetricsRegistry with register/compute/available API
- `coordinator_node/metrics/builtins.py` — 8 built-in metrics (ic, ic_sharpe, hit_rate, mean_return, max_drawdown, sortino_ratio, turnover, model_correlation)
- `coordinator_node/metrics/ensemble_metrics.py` — 3 ensemble-aware metrics (fnc, contribution, ensemble_correlation)
- `coordinator_node/metrics/context.py` — MetricsContext dataclass for cross-model state
- Declared in contract: `CrunchConfig.metrics: list[str]` (active metric names)
- Stored in: `SnapshotRecord.result_summary` JSONB (enriched alongside baseline aggregation)

### Ensemble framework
- `coordinator_node/services/ensemble.py` — weight strategies (inverse_variance, equal_weight), model filters (top_n, min_metric), prediction builder
- `coordinator_node/crunch_config.py` — `EnsembleConfig(name, strategy, model_filter, enabled)`
- Declared in contract: `CrunchConfig.ensembles: list[EnsembleConfig]` (empty = opt-out)
- Virtual models: `__ensemble_{name}__` stored as regular PredictionRecords, scored/tracked normally
- Leaderboard: `include_ensembles=false` param on `/reports/leaderboard`, `/reports/models/global`, `/reports/models/params`

### Custom API endpoints
- `base/node/api/` — drop `.py` files with a `router = APIRouter()` to add endpoints
- Auto-discovered at report-worker startup, no config needed
- Use `API_ROUTES_DIR` env var for custom scan path, `API_ROUTES` for explicit imports
- Full DB access via same `Depends(get_db_session)` pattern as built-in endpoints
- Example: `base/node/api/example_endpoints.py.disabled` (rename to activate)

### Contract discovery
- Workers use `coordinator_node.config_loader.load_config()` instead of `CrunchConfig()`
- Resolution: `CRUNCH_CONFIG_MODULE` env → `runtime_definitions.contracts:CrunchConfig` → engine default
- Operator's config in `node/runtime_definitions/crunch_config.py` is auto-loaded (on PYTHONPATH in Docker)
- Supports both class import (instantiated) and instance import

### Crunch-specific extension points
Set callable paths in env/config:
- `INFERENCE_INPUT_BUILDER`
- `INFERENCE_OUTPUT_VALIDATOR`
- `SCORING_FUNCTION`
- `MODEL_SCORE_AGGREGATOR`
- `LEADERBOARD_RANKER`
- `CHECKPOINT_INTERVAL_SECONDS`

---

## Post-Deployment Verification (Mandatory)

After any change, run (from generated `crunch-node-<name>`):

```bash
# 1) Optional preflight from repo root
coordinator preflight --ports 3000,5432,8000,9091

# 2) Rebuild + start
make deploy

# 3) E2E verification
make verify-e2e

# 4) Structured runtime log capture for analysis
make logs-capture

# 5) Basic API checks
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/reports/models
curl -s http://localhost:8000/reports/leaderboard
```

Artifacts to inspect:
- `RUNBOOK.md` (generated in node workspace)
- `runtime-services.jsonl` (from `make logs-capture`)
- `process-log.jsonl` (generated in workspace root)

Do not declare completion if verification fails.

---

## Sub-skills

Use these focused skills when needed:

- `coordinator-data-sources` → customize data feeds / inference input sources
- `coordinator-prediction-format` → customize inference input/output contracts
- `coordinator-scoring` → customize scoring + ModelScore aggregation
- `coordinator-leaderboard-reports` → customize ranking and report endpoints

(These skill files remain at their existing repository paths for compatibility with the agent harness.)
