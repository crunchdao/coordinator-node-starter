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

When the user wants a new Crunch:

1. Clone this repository.
2. Create `crunch-<name>` (public): model interface, inference schemas, scoring callable, quickstarters.
3. Create `crunch-node-<name>` (private): copy/adapt `node_template/` runtime and deployment files.
4. Configure callable paths in env/config to point to `crunch-<name>` functions.

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

---

## Where To Implement In This Structure

### Stable core contracts
- `coordinator_core/infrastructure/db/db_tables.py`
- `coordinator_core/entities/*`
- `coordinator_core/services/interfaces/*`

### Default runtime template
- `node_template/workers/*`
- `node_template/services/*`
- `node_template/infrastructure/db/*`
- `node_template/config/extensions.py`
- `node_template/config/runtime.py`
- `node_template/extensions/default_callables.py`

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

After any change, run:

```bash
# 1) Rebuild + start
make deploy

# 2) Error scan
sleep 5
docker compose -f docker-compose.yml -f docker-compose-local.yml --env-file .local.env \
  logs score-worker predict-worker report-worker --tail 300 2>&1 \
  | grep -i "error\|exception\|traceback\|failed\|validation" | tail -20

# 3) Service status
docker compose -f docker-compose.yml -f docker-compose-local.yml --env-file .local.env ps

# 4) Basic API checks
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/reports/models
curl -s http://localhost:8000/reports/leaderboard
```

Do not declare completion if verification fails.

---

## Sub-skills

Use these focused skills when needed:

- `coordinator-data-sources` → customize data feeds / inference input sources
- `coordinator-prediction-format` → customize inference input/output contracts
- `coordinator-scoring` → customize scoring + ModelScore aggregation
- `coordinator-leaderboard-reports` → customize ranking and report endpoints

(These skill files remain at their existing repository paths for compatibility with the agent harness.)
