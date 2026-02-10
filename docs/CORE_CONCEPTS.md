# Core Concepts

## Canonical schema + JSONB extension

Protocol-required data is standardized in canonical tables.
Crunch-specific fields go in JSONB payload columns by default.

## Worker split

- Predict worker: model interaction + prediction persistence
- Score worker: scoring + leaderboard generation
- Report worker: read API for models/leaderboards/metrics

## Extension callables

Runtime behavior is overridden by dotted-path callables from config.
This avoids hardcoding Crunch logic in template workers.
