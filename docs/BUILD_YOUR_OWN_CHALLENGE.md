# Build Your Own Challenge

Use this checklist with the coordinator skill before coding.

## Step 1 — Create repositories

- `crunch-<name>` (public)
- `crunch-node-<name>` (private, from `node_template/`)

## Step 2 — Define required contracts (mandatory)

1. **Define Model Interface**
2. **Define inference input**
3. **Define inference output**
4. **Define scoring function**
5. **Define ModelScore**
6. **Define checkpoint interval**

If any is undefined, stop implementation and finalize the design first.

## Step 3 — Wire callable paths

In `crunch-node-<name>` config:

```bash
INFERENCE_INPUT_BUILDER=crunch_<name>.inference:build_input
INFERENCE_OUTPUT_VALIDATOR=crunch_<name>.validation:validate_output
SCORING_FUNCTION=crunch_<name>.scoring:score_prediction
MODEL_SCORE_AGGREGATOR=crunch_<name>.scoring:aggregate_model_scores
LEADERBOARD_RANKER=crunch_<name>.ranking:rank
REPORT_SCHEMA_PROVIDER=crunch_<name>.reporting:report_schema
RAW_INPUT_PROVIDER=crunch_<name>.data:provide_raw_input
GROUND_TRUTH_RESOLVER=crunch_<name>.truth:resolve_ground_truth
CHECKPOINT_INTERVAL_SECONDS=900
```

`REPORT_SCHEMA_PROVIDER` should return canonical frontend report configuration (`leaderboard_columns`, `metrics_widgets`).

The report worker exposes:

- `/reports/schema`
- `/reports/schema/leaderboard-columns`
- `/reports/schema/metrics-widgets`

Built-in starter (BTC + Pyth, enabled by default in local mode):

```bash
RAW_INPUT_PROVIDER=node_template.plugins.pyth_updown_btc:build_raw_input_from_pyth
INFERENCE_OUTPUT_VALIDATOR=node_template.plugins.pyth_updown_btc:validate_probability_up_output
SCORING_FUNCTION=node_template.plugins.pyth_updown_btc:score_brier_probability_up
GROUND_TRUTH_RESOLVER=node_template.plugins.pyth_updown_btc:resolve_ground_truth_from_pyth
MODEL_SCORE_AGGREGATOR=node_template.extensions.default_callables:default_aggregate_model_scores
LEADERBOARD_RANKER=node_template.extensions.default_callables:default_rank_leaderboard
REPORT_SCHEMA_PROVIDER=node_template.extensions.default_callables:default_report_schema
```

## Step 4 — Validate locally

```bash
make deploy
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/reports/models
curl -s http://localhost:8000/reports/leaderboard
```
