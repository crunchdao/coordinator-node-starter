# Coordinator Node Starter

Template source for building Crunch coordinator nodes.

This repository provides:

- `coordinator_core/` — canonical contracts (entities, DB tables, interfaces)
- `node_template/` — runnable default workers/services

## Intended workflow

Create two repositories per Crunch:

1. `crunch-<name>` (public)
   - model interface
   - inference schemas/validation
   - scoring callables
   - quickstarters
2. `crunch-node-<name>` (private)
   - copy/adapt `node_template/`
   - deployment/config for your node

## Required definition points (before implementation)

Define these in your Crunch repos (not in this template):

- Define Model Interface  
  `crunch-<name>/crunch_<name>/tracker.py`
- Define inference input  
  `crunch-<name>/crunch_<name>/inference.py` (builder) + `crunch-node-<name>/node_template/config/extensions.py` (`INFERENCE_INPUT_BUILDER`)
- Define inference output  
  `crunch-<name>/crunch_<name>/validation.py` (schema/validator) + `crunch-node-<name>/node_template/config/extensions.py` (`INFERENCE_OUTPUT_VALIDATOR`)
- Define scoring function  
  `crunch-<name>/crunch_<name>/scoring.py` + `crunch-node-<name>/node_template/config/extensions.py` (`SCORING_FUNCTION`)
- Define ModelScore  
  `crunch-<name>/crunch_<name>/scoring.py` (`aggregate_model_scores`) and optionally `crunch-<name>/crunch_<name>/ranking.py` + `crunch-node-<name>/node_template/config/extensions.py` (`MODEL_SCORE_AGGREGATOR`, `LEADERBOARD_RANKER`)
- Define checkpoint interval  
  `crunch-node-<name>/node_template/config/runtime.py` (`CHECKPOINT_INTERVAL_SECONDS`)

## Built-in starter plugin: BTC up/down with Pyth

The template now includes a reusable plugin at:

- `node_template/plugins/pyth_updown_btc.py`

This gives you:

- raw input from Pyth (BTC/USD latest price)
- inference output validation for `{"p_up": float}`
- Brier-based scoring (`score = 1 - (p_up - y)^2`)
- ground-truth resolution (`y_up` from latest vs entry price)

To enable it in `crunch-node-<name>`:

```bash
RAW_INPUT_PROVIDER=node_template.plugins.pyth_updown_btc:build_raw_input_from_pyth
INFERENCE_OUTPUT_VALIDATOR=node_template.plugins.pyth_updown_btc:validate_probability_up_output
SCORING_FUNCTION=node_template.plugins.pyth_updown_btc:score_brier_probability_up
GROUND_TRUTH_RESOLVER=node_template.plugins.pyth_updown_btc:resolve_ground_truth_from_pyth
```

## Run local template stack

```bash
make deploy
```

Useful endpoints:

- Report API: http://localhost:8000
- UI: http://localhost:3000
- Docs: http://localhost:8080

## Documentation

See `docs/` for concise architecture and bootstrap instructions.
