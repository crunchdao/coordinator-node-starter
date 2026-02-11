# Coordinator Node Starter

Template source for building Crunch coordinator nodes.

This repository provides:

- `coordinator_core/` — canonical contracts (entities, DB tables, interfaces)
- `node_template/` — runnable default workers/services

Legacy status:
- Keep using `coordinator_core/` + `node_template/` for all active development.

## Intended workflow

> New thin-workspace scaffolding is available via CLI:
>
> ```bash
> coordinator init <challenge-slug>
> ```
>
> Spec-driven scaffolding is also supported:
>
> ```bash
> coordinator init --spec path/to/spec.json
> coordinator doctor --spec path/to/spec.json
> ```
>
> `spec.json` must include `"spec_version": "1"`.
>
> This generates `<challenge-slug>/` in the selected output location with:
> - `crunch-node-<challenge-slug>` (thin node wiring)
> - `crunch-<challenge-slug>` (challenge package stubs)

## Launch a local Crunch workspace

From this project root, validate a spec and scaffold a standalone workspace:

```bash
coordinator doctor --spec path/to/spec.json
coordinator init --spec path/to/spec.json --preset realtime --output .
```

Then launch the generated local crunch runtime:

```bash
cd <challenge-slug>/crunch-node-<challenge-slug>
make deploy
make verify-e2e
```

`make verify-e2e` waits until scored predictions and leaderboard entries are available.

Useful endpoints once running:

- Report API: http://localhost:8000
- UI: http://localhost:3000

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

## Built-in starter profile (enabled by default)

Out of the box, local mode uses:

- `node_template/plugins/pyth_updown_btc.py`
- BTC-only fast prediction config (`1m` horizon / `1m` interval)

This starter profile provides:

- Pyth BTC price input
- output validation (`p_up` or density payload)
- default Brier + 3-window leaderboard metrics (`recent`, `steady`, `anchor`)
- optional alternative scoring/ranking profiles (e.g. risk-adjusted Sharpe-like)
- Pyth-based ground-truth resolution

## Run local template stack (end-to-end)

```bash
make deploy
make verify-e2e
```

`make verify-e2e` waits until scored predictions and leaderboard entries are available.

Useful endpoints:

- Report API: http://localhost:8000
- UI: http://localhost:3000
- Docs: http://localhost:8080

For scaffold-first local challenge onboarding, see:

- `docs/ONBOARDING.md`

## Runtime notes (current defaults)

- `predict-worker` and `score-worker` configure INFO logging on startup and emit lifecycle/idle log lines.
  - This keeps the UI Logs tabs useful even when the system is otherwise idle.
- `ScoreService` performs repository rollback attempts after loop exceptions.
  - `DBPredictionRepository`, `DBModelRepository`, and `DBLeaderboardRepository` expose `rollback()` for this recovery path.
- Local `report-ui` mounts config to both:
  - `/app/config`
  - `/app/apps/starter/config`
- Report worker exposes schema endpoints:
  - `/reports/schema`
  - `/reports/schema/leaderboard-columns`
  - `/reports/schema/metrics-widgets`
- `REPORT_SCHEMA_PROVIDER` selects the canonical schema callable used by report worker.
  - FE can merge local override files on top of this canonical schema.
  - Default schema provides `score_recent`, `score_steady`, `score_anchor` fields.

## Documentation

Start here for challenge setup:

- `docs/ONBOARDING.md` — canonical onboarding flow (including typed JSONB schema ownership)

Additional references:

- `docs/BUILD_YOUR_OWN_CHALLENGE.md`
- `docs/DATABASE_SCHEMA.md`
- `docs/`
