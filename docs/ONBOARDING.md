# Onboarding a New Challenge

This is the canonical onboarding flow for a new challenge using the generic coordinator architecture.

## 1) Create the two repositories

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

## 6) Verify end-to-end

```bash
make deploy
curl -s http://localhost:8000/healthz
curl -s http://localhost:8000/reports/models
curl -s http://localhost:8000/reports/leaderboard
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
