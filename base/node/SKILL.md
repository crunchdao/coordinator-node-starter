---
name: starter-challenge-node
summary: Agent instructions for operating node.
---

# Node skill - node

## Primary commands

```bash
make deploy
make verify-e2e
make logs
make logs-capture
make down
make backfill SOURCE=pyth SUBJECT=BTC FROM=2026-01-01 TO=2026-02-01
```

## Workers

| Container | Purpose |
|---|---|
| feed-data-worker | Ingests feed data (Pyth, Binance) |
| predict-worker | Event-driven: feed → models → predictions |
| score-worker | Resolves actuals → scores → snapshots → leaderboard |
| checkpoint-worker | Aggregates snapshots → EmissionCheckpoint |
| report-worker | FastAPI serving all report endpoints |

## Report API

- Health: `http://localhost:8000/healthz`
- Models: `http://localhost:8000/reports/models`
- Leaderboard: `http://localhost:8000/reports/leaderboard`
- Predictions: `http://localhost:8000/reports/predictions`
- Feeds: `http://localhost:8000/reports/feeds`
- Snapshots: `http://localhost:8000/reports/snapshots`
- Checkpoints: `http://localhost:8000/reports/checkpoints`
- Latest emission: `http://localhost:8000/reports/emissions/latest`
- Emission (protocol): `http://localhost:8000/reports/checkpoints/{id}/emission`
- Emission (CLI format): `http://localhost:8000/reports/checkpoints/{id}/emission/cli-format`

## Edit boundaries

- Node-specific config: `.local.env`, `config/callables.env`,
  `config/scheduled_prediction_configs.json`, `deployment/`.
- Runtime contract: `runtime_definitions/contracts.py` (CrunchContract, types, callables).
- Challenge implementation is mounted from `../challenge`.

## Logs and artifacts

- `make logs` streams all service logs from docker compose.
- `make logs-capture` writes structured logs to `runtime-services.jsonl`.
- Use `RUNBOOK.md` for known failure modes and recovery.
