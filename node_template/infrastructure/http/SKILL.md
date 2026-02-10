---
name: coordinator-data-sources
description: Use when defining or changing raw data sources and inference input-building logic for a Crunch node.
---

# Data Sources & Inference Input

> Compatibility note: this skill file remains in `condorgame_backend/infrastructure/http/` for routing; implementation targets are in `node_template/`.

## Goal

Help the user define:
- raw data source(s)
- inference input shape sent to models
- transformation pipeline from source data to model input

## Canonical places to update

- `node_template/services/predict_service.py`
- `node_template/config/extensions.py`
- `node_template/extensions/default_callables.py`
- crunch-specific implementation in `crunch-<name>` (public) and/or `crunch-node-<name>` (private)

## Required decisions to collect

1. source type (API, WS, DB, files, hybrid)
2. refresh cadence and latency requirements
3. canonical raw input structure
4. transformed inference input structure
5. failure/retry policy and fallback behavior

## Extension contract

```bash
INFERENCE_INPUT_BUILDER=crunch_<name>.inference:build_input
```

Contract:
- input: `raw_input: dict`
- output: JSON-serializable `dict` sent to model runner `tick/predict` flow

## Implementation checklist

- [ ] conversion is deterministic and timezone-safe
- [ ] missing/partial data behavior is defined
- [ ] input payload is JSON-serializable
- [ ] integration test covers at least one full predict cycle

## Verification

```bash
make deploy
sleep 5
docker compose -f docker-compose.yml -f docker-compose-local.yml --env-file .local.env \
  logs predict-worker --tail 200
```
