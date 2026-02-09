---
name: coordinator-node-starter
description: Use when working with Crunch competition infrastructure - debugging workers, customizing data sources, scoring, predictions, or leaderboards. Load this first, then sub-skills as needed.
---

# Coordinator Node Starter

Backend for CrunchDAO competitions. Predict/Score/Report workers receive predictions from participant models, score them, and expose leaderboards.

## Architecture

```
Price Sources (CrunchDAO/Pyth)     Model Orchestrator (gRPC)
              ↓                            ↓
        ┌─────────────────────────────────────────┐
        │           Predict Worker                │
        │  fetch prices → tick() → predict()     │
        │            → store predictions          │
        └─────────────────┬───────────────────────┘
                          ↓
        ┌─────────────────────────────────────────┐
        │            Score Worker                 │
        │  load predictions → score vs actual     │
        │     → rolling windows → leaderboard     │
        └─────────────────┬───────────────────────┘
                          ↓
        ┌─────────────────────────────────────────┐
        │           Report Worker (FastAPI)       │
        │  /reports/leaderboard, /models, etc.    │
        └─────────────────────────────────────────┘
```

## Quick Commands

| Command | Purpose |
|---------|---------|
| `make deploy` | Start full stack |
| `make deploy dev` | Start infra only (run workers from IDE) |
| `make logs` | All service logs |
| `make logs SERVICES=predict-worker` | Specific service logs |
| `make restart` | Restart all |
| `make down` | Stop and remove |
| `docker compose ps` | Check service status |

## Debugging Playbook

### Step 1: Check Services Running

```bash
docker compose ps
```

Look for:
- **Exit codes** - non-zero means crash
- **Restart count** - high count means crash loop
- **Status** - should be "running" or "healthy"

### Step 2: Identify Failing Layer

| Symptom | Check This | Command |
|---------|------------|---------|
| Models not connecting | model-orchestrator | `make logs SERVICES=model-orchestrator` |
| Models not receiving ticks | model-orchestrator | `make logs SERVICES=model-orchestrator` |
| Model errors/exceptions | model-orchestrator | `make logs SERVICES=model-orchestrator` |
| Predictions not stored | predict-worker | `make logs SERVICES=predict-worker` |
| Scores not appearing | score-worker | `make logs SERVICES=score-worker` |
| API returning errors | report-worker | `make logs SERVICES=report-worker` |
| DB connection issues | postgres | `make logs SERVICES=postgres` |

### Step 3: Common Failure Patterns

#### "Models not receiving ticks"

**Check model-orchestrator logs:**
```bash
make logs SERVICES=model-orchestrator
```

**Look for:**
- `Connection refused` - orchestrator not ready, model crashed
- `Model not found` - check `models.dev.yml` configuration
- Model not in `RUNNING` state - check `desired_state` in config

**Verify model config:**
```
deployment/model-orchestrator-local/config/models.dev.yml
```

#### "Model returns no values / timeout"

**Check model-orchestrator logs for Python exceptions:**
```bash
make logs SERVICES=model-orchestrator 2>&1 | grep -A 10 "Exception\|Error\|Traceback"
```

**Look for:**
- Import errors in model code
- Runtime exceptions during `tick()` or `predict()`
- Model marked as failed after consecutive failures (default: 100)

**In predict-worker logs:**
```bash
make logs SERVICES=predict-worker
```

Look for: `Tick finished with X success, Y failed and Z timed out`

#### "Predictions not being stored"

**Check predict-worker logs:**
```bash
make logs SERVICES=predict-worker
```

**Look for:**
- DB connection errors
- `predictions got` count - should match model count
- `missing predictions (models sit out)` - models that didn't respond

#### "Scores not appearing"

**This is often NORMAL!** Prediction horizon is typically 1 hour, so scores take 1+ hour to appear.

**If waited long enough, check score-worker:**
```bash
make logs SERVICES=score-worker
```

**Look for:**
- `No predictions to score` - predictions not yet resolvable
- `Scored X predictions, Y failed` - scoring errors
- `No price data found` - price feed issues
- `Minimum score: X` - very negative = potential issues

#### "API not returning data"

**Check report-worker logs:**
```bash
make logs SERVICES=report-worker
```

**Test endpoints directly:**
```bash
curl http://localhost:8000/reports/leaderboard
curl http://localhost:8000/reports/models
```

### Step 4: Database Inspection

**Connect to postgres:**
```bash
docker compose exec postgres psql -U condorgame -d condorgame
```

**Useful queries:**
```sql
-- Check prediction counts
SELECT model_id, COUNT(*) FROM predictions GROUP BY model_id;

-- Check recent predictions
SELECT id, model_id, status, performed_at FROM predictions ORDER BY performed_at DESC LIMIT 10;

-- Check scored predictions
SELECT id, model_id, score_value, score_success FROM predictions WHERE score_scored_at IS NOT NULL ORDER BY score_scored_at DESC LIMIT 10;

-- Check leaderboard
SELECT * FROM leaderboards ORDER BY created_at DESC LIMIT 1;
```

### Step 5: Full Pipeline Trace

To trace a prediction through the entire pipeline:

```bash
# 1. Watch predict-worker create prediction
make logs SERVICES=predict-worker 2>&1 | grep -i "predict\|tick"

# 2. Watch score-worker score it (after horizon passes)
make logs SERVICES=score-worker 2>&1 | grep -i "score\|leaderboard"

# 3. Verify in API
curl http://localhost:8000/reports/leaderboard | jq
```

## Customization Sub-Skills

When you need to customize specific components, read the relevant sub-skill:

| What to Customize | Sub-Skill Location |
|-------------------|-------------------|
| Data sources (prices, features) | `condorgame_backend/infrastructure/http/SKILL.md` |
| Scoring algorithm | `condorgame_backend/services/SKILL.md` |
| Prediction format | `condorgame_backend/entities/SKILL.md` |
| Leaderboard & reports | `condorgame_backend/workers/SKILL.md` |

## Key Files Reference

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Service definitions |
| `docker-compose-local.yml` | Local dev overrides |
| `.local.env` / `.dev.env` | Environment config |
| `deployment/model-orchestrator-local/config/` | Model orchestrator config |
| `condorgame_backend/workers/` | Worker entry points |
| `condorgame_backend/services/` | Business logic |
| `condorgame_backend/entities/` | Domain models |
| `condorgame_backend/infrastructure/` | DB, HTTP, caching |
