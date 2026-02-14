# Thin Node + CLI Onboarding Design

Date: 2026-02-11
Status: Historical design draft (retained for context; terminology kept aligned with current CLI)

> Note: This is an archived planning document. Current CLI scaffolding is pack-based (`--pack`, `--list-packs`) and generates directly into `<name>/`.

## Goal

Improve onboarding so challenge implementers only touch what they must implement, while shared runtime behavior lives in `coordinator_core`.

Key outcomes:

1. Keep challenge repos thin and understandable.
2. Avoid template-copy drift.
3. Enable fast local iteration without reinstall loops.
4. Provide one-command onboarding and diagnostics.

## Primary Direction

Adopt **Thin Node Repos** as default:

- Runtime contracts/services/workers remain centralized in `coordinator_core`.
- Generated challenge workspace includes:
  - `crunch-node-<name>` for config/deployment/wiring
  - `crunch-<name>` for challenge logic (public package)
- `coordinator init <name>` generates under:
  - `<name>/...`

## Ownership Model

### `coordinator_core` (shared runtime)

Owns:

- canonical entities/interfaces/schemas
- DB table contracts and generic worker/service execution model
- CLI entrypoint (`coordinator`)
- validation/diagnostic helpers used by `doctor`

### `crunch-node-<name>` (private thin node)

Owns:

- environment wiring (`.local.env`, callable paths)
- deployment settings/compose files
- optional node-side customizations in:
  - `plugins/` (integrations/adapters/helpers)
  - `extensions/` (callable wiring and override hooks)

Does **not** own copied runtime internals by default.

### `crunch-<name>` (public challenge package)

Owns:

- tracker/model interface
- challenge input/output schemas
- scoring, ranking, report schema callables
- optional public data plugins (`plugins/`)
- optional grouped callable sets (`extensions/`)

## Generated Workspace Layout

```text
<name>/
  README.md
  crunch-node-<name>/
    README.md
    pyproject.toml
    .local.env.example
    deployment/
      README.md
      docker-compose*.yml
    config/
      README.md
      scheduled_prediction_configs.json
      callables.env
    plugins/
      README.md
    extensions/
      README.md
  crunch-<name>/
    README.md
    crunch_<name>/
      tracker.py
      inference.py
      validation.py
      scoring.py
      reporting.py
      schemas/
        README.md
      plugins/
        README.md
      extensions/
        README.md
```

Each key folder includes a short README explaining:

- what belongs here
- what should stay in `coordinator_core`
- public vs private code boundaries

## Local Editability (No Reinstall Loop)

Generated `crunch-node-<name>/pyproject.toml` should use editable local sources for development.

Target behavior:

- edits in repo-local `coordinator_core` are picked up after worker/container restart
- edits in `crunch-<name>` are also picked up after restart
- no repeated reinstall commands required

Production/CI can later switch to pinned released versions.

## CLI Scope

## v1 Commands (approved)

### `coordinator init <name>`

- Scaffold `<name>/...`
- Generate only required challenge stubs
- Wire callable env vars with explicit TODOs
- Create README breadcrumbs in every important folder

### `coordinator doctor`

Validate:

- required env vars and callable path importability
- required callable signatures
- API health and core report endpoints
- model-runner failure markers in logs (e.g. BAD_IMPLEMENTATION/import errors)

### `coordinator dev`

- one command for local startup lifecycle
- wait for readiness
- run e2e verification
- optional logs tail/follow mode

## v2 Commands/Capabilities (approved)

Add full service replacement extension points for advanced users:

- `PREDICT_SERVICE_FACTORY`
- `SCORE_SERVICE_FACTORY`
- `REPORT_APP_FACTORY`

This enables replacing entire loops/apps without forking shared runtime, while keeping v1 onboarding simple.

## Extension Levels

1. **Standard extension (default):** callables in `crunch-<name>`
   - scoring/ranking/report schema/inference adapters
2. **Advanced extension (v2):** service-factory overrides
   - for non-standard orchestration behavior

## UX and Documentation Principles

- Keep onboarding to a short “10-minute path” in top-level docs.
- Move deep details to linked docs.
- Let generated folder READMEs teach placement/ownership in context.
- Enforce YAGNI: generate only required files by default.

## Migration Direction from Current State

1. Keep current repo functional while introducing CLI scaffolding.
2. Start generating new implementations via `coordinator init`.
3. Gradually reduce template-copy expectations and centralize reusable runtime in `coordinator_core`.
4. Introduce v2 service-factory overrides only after v1 stabilizes.

## Success Criteria

- New implementer can scaffold and run end-to-end with <= 3 commands.
- Implementer edits only challenge files + minimal node config.
- Shared runtime upgrades happen centrally with lower drift.
- Local development remains fast (no reinstall loop).