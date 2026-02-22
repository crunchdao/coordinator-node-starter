# Node Context — starter-challenge

## What this is

Standalone node runtime workspace. Contains docker-compose, workers, config, and the report API. Runs the `coordinator-node` engine from PyPI.

## Primary commands

```bash
make deploy                                                    # Build and start all services
make verify-e2e                                                # End-to-end validation
make logs                                                      # Stream all service logs
make logs-capture                                              # Write structured logs to runtime-services.jsonl
make down                                                      # Tear down all services
make backfill SOURCE=pyth SUBJECT=BTC FROM=2026-01-01 TO=2026-02-01  # Backfill historical data
```

## Workers

| Container | Purpose |
|---|---|
| `feed-data-worker` | Ingests feed data (Pyth, Binance) |
| `predict-worker` | Event-driven: feed → models → predictions |
| `score-worker` | Resolves actuals → scores → snapshots → leaderboard |
| `checkpoint-worker` | Aggregates snapshots → EmissionCheckpoint |
| `report-worker` | FastAPI serving all report endpoints |

## Report API

| Endpoint | Description |
|---|---|
| `http://localhost:8000/healthz` | Health check |
| `http://localhost:8000/reports/models` | Registered models |
| `http://localhost:8000/reports/leaderboard` | Current leaderboard |
| `http://localhost:8000/reports/predictions` | Prediction history |
| `http://localhost:8000/reports/feeds` | Active feed subscriptions |
| `http://localhost:8000/reports/snapshots` | Per-model period summaries (enriched with metrics) |
| `http://localhost:8000/reports/checkpoints` | Checkpoint history |
| `http://localhost:8000/reports/emissions/latest` | Latest emission |
| `http://localhost:8000/reports/checkpoints/{id}/emission` | Raw emission (frac64) |
| `http://localhost:8000/reports/checkpoints/{id}/emission/cli-format` | Coordinator-CLI JSON format |

## API Security

Set `API_KEY` in `.local.env` to enable authentication.

- **Admin endpoints** (backfill, checkpoints, `/custom/*`) always require the key when set
- **Public endpoints** (leaderboard, schema, models) stay open
- **Read endpoints** optionally gated via `API_READ_AUTH=true`

## Custom API endpoints

Drop `.py` files in `api/` with a `router = APIRouter()`. Auto-mounted at report-worker startup. Full DB access via `Depends`.

Config: `API_ROUTES_DIR` (default `api/`), `API_ROUTES` (explicit `module:attr` paths).

## Folder map — where to put things

| Folder | Purpose | When to use |
|---|---|---|
| `api/` | Custom FastAPI endpoints | Add any `.py` file with `router = APIRouter()` — auto-discovered at startup. See `api/README.md` for examples with DB access and metrics. |
| `extensions/` | Node-specific callable overrides | Edge-case Python modules needed by the runtime (custom feed providers, specialized scoring helpers). Most customization should go in `runtime_definitions/crunch_config.py` instead. |
| `plugins/` | Node-side integrations | Custom feed providers beyond built-in Pyth/Binance, external API integrations, data enrichment. Use when code needs secrets or calls private APIs that shouldn't be in the challenge package. |
| `runtime_definitions/` | Competition contract | `crunch_config.py` is the primary file — defines all type shapes, callables, and behavior. `contracts.py` is backward compat. |
| `config/` | Runtime configuration | `callables.env` for scoring function path, `scheduled_prediction_configs.json` for prediction schedule and scope. |
| `deployment/` | Local deployment assets | `model-orchestrator-local/` for local model runner config, `report-ui/` for dashboard settings. |
| `scripts/` | Utility scripts (do not edit) | `verify_e2e.py`, `backfill.py`, `check_models.py`, `capture_runtime_logs.py` — called by Makefile targets. |

## Edit boundaries

| What | Where |
|---|---|
| Node env config | `.local.env`, `.env` |
| Callable paths | `config/callables.env` |
| Prediction schedules | `config/scheduled_prediction_configs.json` — **`resolve_after_seconds` must be > feed data interval** (see below) |
| Competition types & behavior | `runtime_definitions/crunch_config.py` (preferred), `runtime_definitions/contracts.py` (backward compat) |
| Custom API endpoints | `api/` |
| Custom callable modules | `extensions/` |
| External integrations / feed providers | `plugins/` |
| Local deployment config | `deployment/` |
| Challenge implementation | Mounted from `../challenge` |

## Prediction schedule constraint

`resolve_after_seconds` in `config/scheduled_prediction_configs.json` controls how long the score-worker waits before fetching ground truth from the feed. **It must be strictly greater than the feed's effective data interval**, otherwise no feed data will exist yet when scoring runs, and all predictions fail to score silently.

- Feed granularity `1s` + poll every `5s` → `resolve_after_seconds` > 5
- Feed granularity `1m` → `resolve_after_seconds` > 60
- Feed granularity `5m` → `resolve_after_seconds` > 300

Always ask the user what `resolve_after_seconds` should be — do not assume a default.

## Logs and artifacts

- `make logs` streams all service logs from docker compose
- `make logs-capture` writes structured logs to `runtime-services.jsonl`
- Known failure modes and recovery: `RUNBOOK.md`
