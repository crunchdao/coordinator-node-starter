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
> coordinator init --spec path/to/spec.json --pack realtime
> coordinator doctor --spec path/to/spec.json --pack realtime
> coordinator init --list-packs
> ```
>
> `spec.json` must include `"spec_version": "1"`.
>
> This generates `<challenge-slug>/` in the selected output location with:
> - `crunch-node-<challenge-slug>` (thin node wiring)
> - `crunch-<challenge-slug>` (challenge package stubs)

## Launch a local Crunch workspace

From this project root, run deterministic setup:

```bash
coordinator preflight --ports 3000,5432,8000,9091
coordinator doctor --spec path/to/spec.json --pack realtime
coordinator init --answers answers.json --spec path/to/spec.json --pack realtime --output .
```

Then launch and verify the generated local crunch runtime:

```bash
cd <challenge-slug>/crunch-node-<challenge-slug>
make deploy
make verify-e2e
make logs-capture
```

`make verify-e2e` waits until scored predictions and leaderboard entries are available.

Useful endpoints once running:

- Report API: http://localhost:8000
- UI: http://localhost:3000

Create two repositories per Crunch:

1. `crunch-<name>` (public)
   - model interface (`tracker.py`)
   - scoring/self-eval logic (`scoring.py`)
   - quickstarters (`examples/`)
2. `crunch-node-<name>` (private)
   - deployment/config for your node
   - callable wiring (`config/callables.env`)
   - runtime callables (`runtime_definitions/`)

## Required definition points (before implementation)

Define these in your Crunch repos (not in this template):

- Define model interface  
  `crunch-<name>/crunch_<name>/tracker.py`
- Define participant quickstarters  
  `crunch-<name>/crunch_<name>/examples/mean_reversion_tracker.py`  
  `crunch-<name>/crunch_<name>/examples/trend_following_tracker.py`  
  `crunch-<name>/crunch_<name>/examples/volatility_regime_tracker.py`
- Define scoring function for local self-eval  
  `crunch-<name>/crunch_<name>/scoring.py`
- Define runtime inference input  
  `crunch-node-<name>/runtime_definitions/inference.py` (`INFERENCE_INPUT_BUILDER`)
- Define runtime inference output validation  
  `crunch-node-<name>/runtime_definitions/validation.py` (`INFERENCE_OUTPUT_VALIDATOR`)
- Define runtime data + ground-truth providers  
  `crunch-node-<name>/runtime_definitions/data.py` (`RAW_INPUT_PROVIDER`, `GROUND_TRUTH_RESOLVER`)
- Define runtime report schema  
  `crunch-node-<name>/runtime_definitions/reporting.py` (`REPORT_SCHEMA_PROVIDER`)
- Define checkpoint interval  
  `crunch-node-<name>/.local.env` (`CHECKPOINT_INTERVAL_SECONDS`)

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
- `docs/flow.md` (standard deterministic flow: answers file + preflight + runbook + process log)

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
