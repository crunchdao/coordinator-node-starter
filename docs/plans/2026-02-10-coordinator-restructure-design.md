# Coordinator Repository Restructure Design

**Date:** 2026-02-10  
**Status:** Validated with stakeholder  
**Scope:** Big-bang architectural refactor (no compatibility shim)

## 1) Objective

Restructure this repository into a reusable coordinator foundation with standardized protocol behavior, while preserving challenge-level flexibility for implementers.

The target operating model is:

- Standardized coordinator base in this repository
- Crunch-specific public contract and scoring in `crunch-<name>`
- Crunch-specific node implementation in `crunch-node-<name>`

This enables fast creation of new competitions without rewriting coordinator internals.

## 2) Confirmed Decisions

1. **Migration strategy:** Big-bang refactor (architecture-first)
2. **Customization defaults:** Concrete defaults in `node-template` (not abstract-only core)
3. **Entity extension:** JSONB-first customization, optional schema extension allowed
4. **Inference contracts:** Optional schema validation support (not enforced)
5. **Core packaging:** Folder now, package later
6. **Day-one goal:** New structure can land even if runtime is temporarily broken
7. **DB standardization:** Single canonical Postgres schema in this repo
8. **Extension mechanism:** Config-driven callable paths
9. **Scoring ownership:** Scoring callable lives in `crunch-<name>`
10. **Dependency mode:** Local source/path in development first
11. **Config source of truth:** Env/config file only (no DB override)
12. **Checkpoint interval:** Configurable per crunch-node
13. **Backward compatibility:** No old import/path shim
14. **Public crunch repo ownership:** Contract + scoring + schemas + validation artifacts

## 3) Target Repository Layout

```text
.
├── coordinator_core/        # protocol-level stable foundations
├── node_template/           # runnable default coordinator implementation
├── data/                    # data files used by services
├── deployment/              # deployment assets
├── docs/
│   └── plans/
└── ...
```

### `coordinator_core/` responsibilities

- Canonical schema definitions and migration baseline
- Immutable protocol-facing entity contracts
- Stable repository/service interfaces
- Shared utilities used across runtimes

### `node_template/` responsibilities

- Default Predict/Score/Report workers
- Default inference input/output handling
- Default scoring and ranking behavior
- Scheduler/checkpoint runtime behavior
- Callable resolver (dotted path import from config)
- JSONB serialization/deserialization helpers

## 4) Canonical Postgres Model + JSONB Strategy

The repository defines one canonical schema for coordinator protocol needs.

### Required default tables

- `models`
- `predictions`
- `model_scores` (and snapshots/history)
- `leaderboards`
- `prediction_configs`
- `checkpoints`
- `emission_checkpoints`

### Extension approach

Use designated JSONB fields by default, for example:

- `models.meta_jsonb`
- `predictions.inference_input_jsonb`
- `predictions.inference_output_jsonb`
- `predictions.meta_jsonb`
- `model_scores.score_payload_jsonb`
- `leaderboards.meta_jsonb`
- `checkpoints.meta_jsonb`

Implementers may add typed columns or extra tables in `crunch-node-<name>` when needed, but baseline workers rely on canonical fields plus known JSONB slots.

## 5) Inference/Scoring Contract and Plug-in Model

`crunch-<name>` (public) owns:

- Base model interface
- Inference input/output schemas
- Validation helpers
- Scoring callable(s)

`node-template` loads behavior through env/config callable paths.

### Example config keys

- `INFERENCE_INPUT_BUILDER=crunch_x.inference:build_input`
- `INFERENCE_OUTPUT_VALIDATOR=crunch_x.validation:validate_output` (optional)
- `SCORING_FUNCTION=crunch_x.scoring:score_prediction`
- `MODEL_SCORE_AGGREGATOR=crunch_x.scoring:aggregate_model_scores` (optional)
- `LEADERBOARD_RANKER=crunch_x.ranking:rank` (optional)

### Runtime flow

1. Predict worker fetches raw source data
2. Input builder creates model-facing inference payload
3. Model output is received and optionally validated
4. Prediction + inference IO payloads persisted (canonical + JSONB)
5. Score worker resolves truth and calls configured scoring callable
6. ModelScore payload persisted in canonical structure + JSONB
7. Leaderboard built via default or configured ranking callable

## 6) Migration Plan (Big-Bang)

1. Create `coordinator_core/` contracts and canonical schema models
2. Create `node_template/` runnable default workers/services
3. Remove legacy backend package paths entirely
4. Repoint deployment and runtime imports to new structure
5. Add callable resolver + startup fail-fast validation
6. Rework docs around two-repo usage model
7. Add baseline tests for resolver, JSONB payload handling, and scoring pipeline

## 7) Risks and Mitigations

- **Broken imports after hard cut**  
  Mitigation: exhaustive import rewrite + static checks

- **Bad callable config at runtime**  
  Mitigation: startup signature/import validation with explicit error logs

- **JSONB payload drift**  
  Mitigation: schema helpers + optional validation path

- **Scoring/ranking inconsistency**  
  Mitigation: deterministic defaults and fixture-based integration tests

## 8) Non-Goals (for this refactor)

- Immediate extraction of `coordinator_core` as pip-install package
- Backward compatibility layer for legacy backend paths
- DB-driven dynamic callable override

## 9) Usage Model After Refactor

To launch a new crunch:

1. Create **`crunch-<name>`** (public): interface, schemas, validation, scoring, quickstarters
2. Create **`crunch-node-<name>`** (private): node implementation, config paths, deployment

This repository acts as the standardized coordinator base and template source.

## 10) Deferred Items (Explicitly Parked)

- Implement persisted checkpoint execution loop in `node_template` services
  - Write/read `checkpoints` and `emission_checkpoints` as part of worker runtime
  - Keep `CHECKPOINT_INTERVAL_SECONDS` as the config source of truth
  - Add tests for checkpoint persistence and emission cadence

Status: deferred by stakeholder decision (do later).

## 11) Progress Snapshot

Completed in migration work:

- Runtime wiring moved to `node_template` workers/services
- Full report API instantiated:
  - `/reports/models`
  - `/reports/leaderboard`
  - `/reports/models/global`
  - `/reports/models/params`
  - `/reports/predictions`
- Extension callables wired end-to-end (input builder, output validator, scoring, model-score aggregation, leaderboard ranking)
- Docs and bootstrap guidance rewritten to concise template-first model (`crunch-<name>` + `crunch-node-<name>`)
