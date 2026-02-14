# Contract-Based Architecture: 10 Callables → 3 + Contract

**Date:** 2026-02-11
**Status:** Approved

## Problem

The current architecture requires 10 env-configured callables per challenge. Seven of these are plumbing that rarely needs customization. Data shapes (input, output, score) are defined in multiple places: contracts.py, validators, builders, report schemas.

## Design

Replace 7 Tier 2 callables with a single Pydantic `CrunchContract` class. The runtime reads the contract to validate, aggregate, rank, and generate report schemas automatically.

### The Contract

```python
# runtime_definitions/contracts.py

from pydantic import BaseModel, Field


class InferenceInput(BaseModel):
    symbol: str
    asof_ts: int
    candles_1m: list[dict]


class InferenceOutput(BaseModel):
    value: float = Field(ge=0.0, le=1.0)


class ScoreResult(BaseModel):
    value: float
    success: bool = True
    failed_reason: str | None = None


class AggregationWindow(BaseModel):
    hours: int = Field(ge=1)


class Aggregation(BaseModel):
    windows: dict[str, AggregationWindow] = {
        "score_recent": AggregationWindow(hours=24),
        "score_steady": AggregationWindow(hours=72),
        "score_anchor": AggregationWindow(hours=168),
    }
    ranking_key: str = "score_recent"
    ranking_direction: str = "desc"


class CrunchContract(BaseModel):
    input_type = InferenceInput
    output_type = InferenceOutput
    score_type = ScoreResult
    aggregation: Aggregation = Aggregation()
```

### Tier 1 — Remain as Callables

These three define the challenge identity and stay as `module:callable` env vars:

- **SCORING_FUNCTION** — scores a prediction against ground truth
- **RAW_INPUT_PROVIDER** — fetches live data for model input
- **GROUND_TRUTH_RESOLVER** — resolves what "correct" was

### Tier 2 — Replaced by Contract

| Old callable | Replaced by |
|---|---|
| `INFERENCE_INPUT_BUILDER` | `contract.input_type(**raw_input)` |
| `INFERENCE_OUTPUT_VALIDATOR` | `contract.output_type(**model_output)` |
| `MODEL_SCORE_AGGREGATOR` | Runtime reads `contract.aggregation.windows` |
| `LEADERBOARD_RANKER` | Runtime reads `contract.aggregation.ranking_key/direction` |
| `REPORT_SCHEMA_PROVIDER` | Auto-generated from `contract.aggregation` |
| `PREDICTION_SCOPE_BUILDER` | Baked into runtime (pass-through) |
| `PREDICT_CALL_BUILDER` | Baked into runtime (pass-through) |

### Runtime Changes

**predict_worker** loads contract, uses types for validation:
```python
contract = CrunchContract()
validated_input = contract.input_type(**raw_input)
validated_output = contract.output_type(**model_output)
```

**score_worker** loads contract, uses aggregation config:
```python
contract = CrunchContract()
for window_name, window in contract.aggregation.windows.items():
    cutoff = now - timedelta(hours=window.hours)
    metrics[window_name] = mean(scores since cutoff)

entries.sort(
    key=lambda e: e[contract.aggregation.ranking_key],
    reverse=(contract.aggregation.ranking_direction == "desc"),
)
```

**report_worker** auto-generates schema from contract:
- Leaderboard columns from `aggregation.windows` keys
- Chart series from the same window names
- No hand-written 100-line report schema template

### Files Removed

- `runtime_definitions/inference.py` (1-liner pass-through)
- `runtime_definitions/validation.py` (delegates to contracts.py)
- `runtime_definitions/reporting.py` (100-line hand-written schema)
- `coordinator_runtime/defaults.py` (thin wrappers around node_template defaults)

### Files Modified

- `runtime_definitions/contracts.py` — becomes the CrunchContract
- `node_template/config/extensions.py` — shrinks from 10 fields to 3
- `node_template/workers/predict_worker.py` — uses contract types
- `node_template/workers/score_worker.py` — uses contract aggregation
- `node_template/workers/report_worker.py` — auto-generates schema
- `node_template/services/predict_service.py` — drops 4 callable params
- `node_template/services/score_service.py` — drops 2 callable params
- `coordinator_core/cli/init_config.py` — CALLABLE_ORDER shrinks to 3
- Pack JSON files — callables shrink to 3 entries
- Scaffold templates — remove deleted template files

### Migration

The env-based callable system stays for Tier 1. The 7 removed env vars become no-ops (ignored if present). No breaking change for existing deployed nodes — `ExtensionSettings` can fall back gracefully.
