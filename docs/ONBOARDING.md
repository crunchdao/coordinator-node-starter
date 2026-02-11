# Onboarding a New Challenge

This is the canonical onboarding flow for a new challenge using the generic coordinator architecture.

## 1) Create the two repositories

You can scaffold both with the CLI:

```bash
coordinator init <name>
```

Or use a spec file (JSON) for agent-generated setup:

```bash
coordinator init --spec path/to/spec.json
coordinator doctor --spec path/to/spec.json
```

This creates:

- `<name>/crunch-node-<name>`
- `<name>/crunch-<name>`

Run from the generated node folder:

```bash
cd <name>/crunch-node-<name>
make deploy
make verify-e2e
```

Minimal `spec.json` example (note the required `spec_version`):

```json
{
  "spec_version": "1",
  "name": "btc-trader",
  "crunch_id": "starter-challenge",
  "model_base_classname": "crunch_btc_trader.tracker.TrackerBase",
  "checkpoint_interval_seconds": 60,
  "callables": {
    "SCORING_FUNCTION": "crunch_btc_trader.scoring:score_prediction",
    "REPORT_SCHEMA_PROVIDER": "crunch_btc_trader.reporting:report_schema"
  },
  "scheduled_prediction_configs": [
    {
      "scope_key": "default",
      "scope_template": {"asset": "BTC", "horizon_seconds": 60, "step_seconds": 60},
      "schedule": {"every_seconds": 60},
      "active": true,
      "order": 0
    }
  ]
}
```

Manual structure reference:

1. **Public challenge repo**: `crunch-<name>`
   - challenge schemas
   - challenge callables
   - model base class and examples
2. **Private node repo**: `crunch-node-<name>`
   - runtime/deployment config
   - worker wiring (from this starter)

## 2) Define the JSONB schemas in your challenge package

The database is intentionally generic. Challenge-specific structure lives in JSONB and is **typed in your challenge code**.

Define typed schemas (Pydantic/dataclasses) for:

- core envelope contracts live in `coordinator_core/schemas/payload_contracts.py`
- challenge-specific payload schemas live in your challenge package (`crunch_<name>/...`)

- `scheduled_prediction_configs.scope_template_jsonb`
- `scheduled_prediction_configs.schedule_jsonb`
- `predictions.scope_jsonb`
- `predictions.inference_input_jsonb`
- `predictions.inference_output_jsonb`
- score payloads in:
  - `models.overall_score_jsonb`
  - `model_scores.score_payload_jsonb`

Recommended pattern:

- core envelope stays stable (`metrics`, `ranking`, `payload`)
- challenge payload schema lives inside `payload`

## 3) Implement and export challenge callables

Your challenge package should provide callable entrypoints for:

- inference input builder
- inference output validator
- prediction scope builder
- predict call builder
- ground-truth resolver
- prediction scoring
- model-score aggregation
- leaderboard ranking

## 4) Wire callables via environment variables

Set dotted paths in node runtime config:

- `INFERENCE_INPUT_BUILDER`
- `INFERENCE_OUTPUT_VALIDATOR`
- `PREDICTION_SCOPE_BUILDER`
- `PREDICT_CALL_BUILDER`
- `GROUND_TRUTH_RESOLVER`
- `SCORING_FUNCTION`
- `MODEL_SCORE_AGGREGATOR`
- `LEADERBOARD_RANKER`
- `REPORT_SCHEMA_PROVIDER`

## 5) Configure scheduled prediction configs

Use rows in `scheduled_prediction_configs` to define what gets predicted and how often:

- `scope_key`
- `scope_template_jsonb`
- `schedule_jsonb`
- `active`, `order`

Predict worker reads active rows, builds scope/predict calls, and writes predictions with:

- `prediction_config_id`
- `scope_key`
- `scope_jsonb`

## 6) Define report schema contract for UI sync

Expose canonical report schema from backend through `REPORT_SCHEMA_PROVIDER`.

The report worker serves:

- `GET /reports/schema`
- `GET /reports/schema/leaderboard-columns`
- `GET /reports/schema/metrics-widgets`

Recommended FE behavior:

1. fetch backend schema (canonical)
2. merge local override files (labels/order/visibility)
3. warn when override keys are unknown to backend schema

## 7) Verify end-to-end

```bash
make deploy
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/reports/models
curl -s http://localhost:8000/reports/leaderboard
curl -s http://localhost:8000/reports/schema
```

## JSONB ownership summary

| JSONB field | Schema owner |
|---|---|
| `scheduled_prediction_configs.scope_template_jsonb` | challenge package |
| `scheduled_prediction_configs.schedule_jsonb` | challenge package |
| `predictions.scope_jsonb` | challenge package |
| `predictions.inference_input_jsonb` | challenge package |
| `predictions.inference_output_jsonb` | challenge package |
| `models.overall_score_jsonb` | core envelope + challenge payload |
| `model_scores.score_payload_jsonb` | core envelope + challenge payload |
| `leaderboards.entries_jsonb` | core entry + optional challenge extras |
