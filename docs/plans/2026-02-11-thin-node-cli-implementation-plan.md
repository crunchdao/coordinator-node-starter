# Thin Node CLI Implementation Plan

Date: 2026-02-11
Related design: `docs/plans/2026-02-11-thin-node-cli-onboarding-design.md`
Status: Ready for implementation

## Scope

Implement v1 CLI workflow inside `coordinator_core`:

1. `coordinator init <name>`
2. `coordinator doctor`
3. `coordinator dev`

Generate challenge workspaces into `crunch-implementations/<name>/` with minimal required files and folder-level README guidance.

Naming convention: use `plugins/` and `extensions/` folders (do not generate `private_plugins/`).

---

## Milestone 0 — Foundation and guardrails

### Tasks

- [ ] Add CLI package structure (e.g. `coordinator_core/cli/`)
- [ ] Add CLI entrypoint (`coordinator`) in `pyproject.toml`
- [ ] Add shared helpers:
  - [ ] slug/name validation (`btc-trader` format)
  - [ ] path resolution helpers
  - [ ] console logging helpers
- [ ] Decide and lock command framework (prefer stdlib `argparse` for low dependency overhead)

### Acceptance criteria

- `uv run coordinator --help` works
- Command skeleton prints help for `init`, `doctor`, `dev`

---

## Milestone 1 — `coordinator init <name>`

### Tasks

- [ ] Add templates directory for generated files
- [ ] Generate workspace at:
  - `crunch-implementations/<name>/crunch-node-<name>/`
  - `crunch-implementations/<name>/crunch-<name>/`
- [ ] Generate node project files:
  - [ ] `README.md`
  - [ ] `pyproject.toml` with editable local sources:
    - `coordinator-core -> ../../..` (editable)
    - `crunch-<name> -> ../crunch-<name>` (editable)
  - [ ] `.local.env.example`
  - [ ] `config/callables.env`
  - [ ] `config/scheduled_prediction_configs.json`
  - [ ] `deployment/README.md`
  - [ ] `plugins/README.md`
  - [ ] `extensions/README.md`
- [ ] Generate public challenge package files:
  - [ ] `README.md`
  - [ ] `crunch_<name>/tracker.py`
  - [ ] `crunch_<name>/inference.py`
  - [ ] `crunch_<name>/validation.py`
  - [ ] `crunch_<name>/scoring.py`
  - [ ] `crunch_<name>/reporting.py`
  - [ ] `crunch_<name>/schemas/README.md`
  - [ ] `crunch_<name>/plugins/README.md`
  - [ ] `crunch_<name>/extensions/README.md`
- [ ] Generate folder READMEs that explain ownership and where to put code
- [ ] Add overwrite behavior flags:
  - [ ] default: fail if target exists
  - [ ] optional: `--force`

### Acceptance criteria

- One command creates runnable, understandable skeleton
- Generated tree contains only required stub files
- README guidance is present in each major folder

---

## Milestone 2 — `coordinator doctor`

### Tasks

- [ ] Validate required files exist in current node workspace
- [ ] Validate env values for required callable paths
- [ ] Import and signature-check required callables
- [ ] Validate report API availability:
  - [ ] `/healthz`
  - [ ] `/reports/models`
  - [ ] `/reports/leaderboard`
  - [ ] `/reports/schema`
- [ ] Validate model-orchestrator logs for failure markers:
  - `BAD_IMPLEMENTATION`
  - `No Inherited class found`
  - `Import error occurred`
- [ ] Human-readable pass/fail report + non-zero exit on failure

### Acceptance criteria

- `coordinator doctor` pinpoints miswired paths and setup failures quickly
- Failures are actionable (exact file/var/callable marker shown)

---

## Milestone 3 — `coordinator dev`

### Tasks

- [ ] Wrap local lifecycle for current node workspace:
  - [ ] compose up/build
  - [ ] optional clean/down flags
  - [ ] readiness wait
  - [ ] run e2e verification
- [ ] Add optional flags:
  - [ ] `--skip-build`
  - [ ] `--skip-e2e`
  - [ ] `--tail-logs`
- [ ] Reuse doctor/e2e checks where possible

### Acceptance criteria

- `coordinator dev` gives a reliable one-command local bring-up
- output clearly states URLs, active models, and verification result

---

## Milestone 4 — Docs and onboarding consolidation

### Tasks

- [ ] Update root `README.md` with CLI-first flow
- [ ] Update `docs/ONBOARDING.md` to reference `init/doctor/dev`
- [ ] Add “thin node vs advanced extension” section
- [ ] Add migration note for existing copied-node projects

### Acceptance criteria

- New user can onboard from docs using <= 3 commands

---

## Testing Plan

### Unit tests

- [ ] name validation
- [ ] template rendering
- [ ] init path safety and overwrite behavior
- [ ] callable import/signature checks for doctor
- [ ] log marker detection
- [ ] command argument parsing and error handling

### Integration tests

- [ ] init generates expected file tree
- [ ] doctor succeeds on healthy local workspace
- [ ] doctor fails with bad callable path and shows helpful message

---

## PR slicing (recommended)

### PR 1 (smallest useful)

- CLI skeleton + `init`
- templates + generated README breadcrumbs
- tests for init
- docs update for init

### PR 2

- `doctor` command
- callable/import/signature checks
- endpoint + log-marker checks
- doctor tests

### PR 3

- `dev` command wrapper
- run lifecycle + e2e integration
- dev tests and docs

### PR 4

- polish and migration helpers
- optional quality-of-life flags

---

## Deferred to v2 (explicit)

- service-level override factories:
  - `PREDICT_SERVICE_FACTORY`
  - `SCORE_SERVICE_FACTORY`
  - `REPORT_APP_FACTORY`

These remain out of v1 scope to keep onboarding simple.

---

## Risks and mitigations

- **Risk:** relative editable paths break when run from unexpected cwd
  - **Mitigation:** resolve absolute workspace root before rendering templates
- **Risk:** local/prod behavior drift due to editable installs
  - **Mitigation:** document dev mode vs pinned prod mode explicitly
- **Risk:** command complexity grows too quickly
  - **Mitigation:** keep v1 flags minimal, defer advanced knobs

---

## Definition of Done (v1)

- `coordinator init <name>` creates thin, documented workspace in `crunch-implementations/<name>/`
- `coordinator doctor` catches common misconfigurations and model setup failures
- `coordinator dev` runs local stack and verifies readiness/e2e
- docs reflect the new onboarding default
