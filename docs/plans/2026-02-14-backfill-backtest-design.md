# Backfill & Backtest Design

## Overview

Add historical data backfill triggered from the coordinator UI, stored as Hive-partitioned parquet files, served via HTTP endpoints, and consumed by a standardised backtest harness in the challenge package. Model code is identical between backtest and production.

## Architecture

```
Coordinator (cloud)                          Competitor (local)
┌──────────────────────────┐                ┌──────────────────────────┐
│  UI: Backfill Form       │                │  challenge package       │
│    ↓ POST /backfill      │                │                          │
│  BackfillService         │                │  BacktestClient          │
│    ↓ pages from provider │                │    → pulls parquet from  │
│  ParquetBackfillSink     │                │      coordinator API     │
│    ↓                     │                │    → caches in .cache/   │
│  data/backfill/          │  GET /data/    │                          │
│    {source}/{subject}/   │ ←──────────────│  BacktestRunner          │
│    {kind}/{granularity}/ │  backfill/...  │    → reads cached parquet│
│    YYYY-MM-DD.parquet    │                │    → tick() → predict()  │
│                          │                │    → scores, metrics     │
│  backfill_jobs table     │                │    → returns DataFrames  │
│    (status, cursor,      │                │                          │
│     progress)            │                └──────────────────────────┘
└──────────────────────────┘
```

## 1. Backfill Infrastructure

### Backfill Jobs Table

New `backfill_jobs` table in Postgres:

| Column | Type | Description |
|---|---|---|
| `id` | text PK | UUID |
| `source` | text | Feed source (must match configured feed) |
| `subject` | text | Asset |
| `kind` | text | tick/candle |
| `granularity` | text | 1s, 1m, etc. |
| `start_ts` | timestamp | Requested range start |
| `end_ts` | timestamp | Requested range end |
| `cursor_ts` | timestamp | Current progress (enables resume) |
| `records_written` | int | Total records written so far |
| `pages_fetched` | int | Total pages fetched so far |
| `status` | text | pending → running → completed \| failed |
| `error` | text | Failure reason if any |
| `created_at` | timestamp | Job creation time |
| `updated_at` | timestamp | Last progress update |

### Parquet Writer

`ParquetBackfillSink` replaces `DBFeedRecordRepository` as the backfill sink:
- Writes Hive-partitioned parquet to `data/backfill/{source}/{subject}/{kind}/{granularity}/YYYY-MM-DD.parquet`
- One file per day, sorted by `ts_event`
- Overlapping backfills merge and deduplicate by `ts_event`

### Modified BackfillService

The existing `BackfillService` accepts a `ParquetBackfillSink` instead of the DB repository:
- Updates `backfill_jobs` row after each page (cursor, records_written)
- On restart, reads `cursor_ts` from the job and resumes
- Only one backfill runs at a time

## 2. Parquet Schema

Each daily parquet file has flattened typed columns:

| Column | Type | Description |
|---|---|---|
| `ts_event` | timestamp[us, UTC] | Event timestamp |
| `source` | string | Feed source |
| `subject` | string | Asset |
| `kind` | string | tick/candle |
| `granularity` | string | 1s, 1m, etc. |
| `open` | float64 | From values |
| `high` | float64 | From values |
| `low` | float64 | From values |
| `close` | float64 | From values |
| `volume` | float64 | From values |
| `meta` | string (JSON) | Non-standard fields fallback |

## 3. API Endpoints

### Backfill Management (report worker)

- `GET /reports/backfill/feeds` — configured feeds eligible for backfill (reuses `list_indexed_feeds()`)
- `POST /reports/backfill` — start a backfill job. Body: `{ source, subject, kind, granularity, start, end }`. Validates feed exists, creates job row, starts async backfill. Returns 409 if a backfill is already running.
- `GET /reports/backfill/jobs` — list all backfill jobs with status and progress
- `GET /reports/backfill/jobs/{job_id}` — single job detail with cursor, records written, percentage estimate

### Data Serving

- `GET /data/backfill/index` — manifest of available parquet files:
  ```json
  [
    {"path": "binance/BTC/candle/1m/2026-01-15.parquet", "records": 1440, "size_bytes": 48200, "date": "2026-01-15"}
  ]
  ```
- `GET /data/backfill/{source}/{subject}/{kind}/{granularity}/{filename}` — serves raw parquet file for download

## 4. UI Integration

Backfill section in the coordinator webapp:

1. Loads configured feeds from `GET /reports/backfill/feeds`
2. Dropdown to select feed, date picker for start/end
3. "Run Backfill" button → `POST /reports/backfill`
4. Progress view polls `GET /reports/backfill/jobs/{id}` — shows progress bar (cursor between start/end), records written, status
5. History of past backfill runs with status

## 5. Challenge Package Backtest Harness

Lives in the challenge package (e.g. `starter_challenge/backtest.py`). No dependency on `coordinator-node`.

### BacktestClient

Thin HTTP client for data fetching with transparent local cache:

```python
client = BacktestClient(coordinator_url="http://coordinator:8000")
client.pull(subject="BTC", start="2026-01-01", end="2026-02-01")
```

- Calls `/data/backfill/index` to discover available files
- Downloads matching parquet files to `.cache/backtest/{source}/{subject}/{kind}/{granularity}/`
- Skips files already cached
- `refresh=True` to force re-download

### BacktestRunner

Replay engine. Separate from `TrackerBase` — operates on tracker instances:

```python
result = BacktestRunner(model=MyTracker()).run(
    subject="BTC", start="2026-01-01", end="2026-02-01"
)
```

Replay loop:
1. Reads cached parquet files in chronological order
2. Builds rolling windows (same `window_size` as production `FeedReader`)
3. Calls `model.tick(data)` with each window
4. Calls `model.predict(**scope)` at intervals matching the contract's `PredictionScope`
5. Scores each prediction against actual future data using the challenge's `score_prediction()` function
6. Computes rolling window metrics matching production (`score_recent`, `score_steady`, `score_anchor`)

### BacktestResult

Returns notebook-friendly objects:

- `result.predictions_df` — DataFrame of all predictions with timestamps, outputs, scores
- `result.metrics` — dict of rolling window aggregates matching the production contract
- `result.summary()` — formatted summary table

All pandas DataFrames, render natively in Jupyter.

### Usage

```python
from starter_challenge.backtest import BacktestClient, BacktestRunner
from my_model import MyTracker

client = BacktestClient("http://coordinator-url:8000")
client.pull(subject="BTC", start="2026-01-01", end="2026-02-01")

result = BacktestRunner(model=MyTracker()).run(
    subject="BTC", start="2026-01-01", end="2026-02-01"
)

result.predictions_df   # renders as table in notebook
result.metrics           # {'score_recent': 0.42, 'score_steady': 0.38, 'score_anchor': 0.35}
result.summary()         # formatted output
```

## 6. Key Design Decisions

- **Parquet as primary storage for historical data** — Postgres stays for live/recent data only. Parquet is purpose-built for bulk columnar reads by models.
- **Hive-style partitioning** — `{source}/{subject}/{kind}/{granularity}/YYYY-MM-DD.parquet`. Maps to feed dimensions, easy to browse and prune.
- **Push-based replay** — BacktestRunner drives `tick()` → `predict()` exactly as production. Model code unchanged.
- **Separate from TrackerBase** — BacktestRunner is a tool that operates on trackers. TrackerBase stays minimal (`tick`, `predict`).
- **Transparent caching** — First backtest run pulls data, subsequent runs are fully offline.
- **DB-persisted backfill jobs** — Survives restarts, resumable from cursor, UI always has history.
- **Feeds must be pre-configured** — No free-form backfill. UI shows only feeds already configured in the system.

## Files to Create/Modify

### Coordinator-node (new)
- `coordinator_node/db/tables/backfill.py` — BackfillJobRow table
- `coordinator_node/db/backfill_jobs.py` — DBBackfillJobRepository
- `coordinator_node/services/parquet_sink.py` — ParquetBackfillSink (Hive-partitioned writer)
- Report worker: new backfill + data-serving endpoints

### Coordinator-node (modify)
- `coordinator_node/services/backfill.py` — accept ParquetBackfillSink, update job progress
- `coordinator_node/db/init_db.py` — add backfill_jobs table migration
- `docker-compose.yml` — mount `data/backfill` volume

### Challenge package (new)
- `starter_challenge/backtest.py` — BacktestClient, BacktestRunner, BacktestResult
