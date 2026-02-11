---
name: coordinator-prediction-format
description: Use when defining or changing model interface, inference input/output contracts, and prediction payload validation for a Crunch.
---

# Prediction Format & Inference Contracts

> Compatibility note: this skill file may be mirrored under legacy backend paths for agent routing, but targets the **new structure** (`coordinator_core/` + `node_template/`).

## Goal

Help the user define and implement:
- model interface
- inference input
- inference output
- output validation behavior

## Canonical places to update

- `coordinator_core/entities/prediction.py`
- `coordinator_core/infrastructure/db/db_tables.py` (`inference_input_jsonb`, `inference_output_jsonb`)
- `node_template/services/predict_service.py`
- `node_template/config/extensions.py`
- `node_template/extensions/default_callables.py`

## Required decisions to collect from the user

1. `predict` output shape (point, category, distribution, custom object)
2. expected cardinality (e.g. horizon/step count rules)
3. invalid output policy (mark failed vs transform vs fallback)
4. validator contract and callable path

## Extension contracts

- Input builder: `build_input(raw_input) -> dict`
- Output validator: `validate_output(inference_output) -> dict`

Configure through env/config:

```bash
INFERENCE_INPUT_BUILDER=crunch_<name>.inference:build_input
INFERENCE_OUTPUT_VALIDATOR=crunch_<name>.validation:validate_output
```

## Implementation checklist

- [ ] Update `crunch-<name>` public contract docs/examples
- [ ] Ensure outputs are JSON-serializable
- [ ] Persist canonical fields + JSONB payloads
- [ ] Add tests for valid, invalid, edge-case outputs
- [ ] Verify predict worker marks validator failures clearly

## Verification

```bash
make deploy
sleep 5
docker compose -f docker-compose.yml -f docker-compose-local.yml --env-file .local.env \
  logs predict-worker --tail 200
```
