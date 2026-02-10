---
name: coordinator-leaderboard-reports
description: Use when defining leaderboard ranking behavior and report API outputs for a Crunch node.
---

# Leaderboard & Report Endpoints

> Compatibility note: this skill file remains in `condorgame_backend/workers/` for routing; implementation targets are in `node_template/`.

## Goal

Help the user define and implement:
- leaderboard ranking semantics
- API response shape for reports
- metrics exposure for coordinator UI and external consumers

## Canonical places to update

- `node_template/services/score_service.py` (aggregator + ranker integration)
- `node_template/workers/report_worker.py` (FastAPI routes)
- `node_template/infrastructure/db/repositories.py` (leaderboard persistence/retrieval)

## Required decisions to collect

1. ranking order and tie-breakers
2. which score fields are public (`recent`, `steady`, `anchor`, custom)
3. endpoint set required by consumer (`/reports/models`, `/reports/leaderboard`, optional extras)
4. backward-compatibility needs for existing frontend expectations

## Extension contracts

```bash
MODEL_SCORE_AGGREGATOR=crunch_<name>.scoring:aggregate_model_scores
LEADERBOARD_RANKER=crunch_<name>.ranking:rank
```

## Implementation checklist

- [ ] ranking output includes deterministic rank values
- [ ] report responses are stable and documented
- [ ] empty-state behavior is explicit (`[]` vs error)
- [ ] endpoint tests exist for both non-empty and empty data

## Verification

```bash
make deploy
sleep 5
curl -s http://localhost:8000/reports/models
curl -s http://localhost:8000/reports/leaderboard
docker compose -f docker-compose.yml -f docker-compose-local.yml --env-file .local.env \
  logs report-worker --tail 200
```
