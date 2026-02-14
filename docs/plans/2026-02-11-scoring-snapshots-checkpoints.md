# Scoring, Snapshots & Checkpoints

## Overview

Three-tier aggregation pipeline: scores → snapshots → checkpoints → payouts.

## Cadences

| Stage | Frequency | Trigger | Output |
|---|---|---|---|
| **Predict** | every tick/interval | feed data arrives | PredictionRecord (PENDING) |
| **Score** | every N seconds (e.g. 60s) | polling timer | ScoreRecord per prediction, InputRecord actuals resolved |
| **Snapshot** | same cadence as score (runs after score) | score cycle completes | SnapshotRecord per model (period summary) |
| **Checkpoint** | weekly | timer / manual | CheckpointRecord (final ranking, pushed on-chain for payouts) |

## Data Flow

```
Predictions (millions/week, per tick)
    ↓ score cycle batches them
Scores (per prediction, written each cycle)
    ↓ snapshot condenses per model
Snapshots (per model per cycle, e.g. every 60s)
    ↓ checkpoint aggregates snapshots
Checkpoints (per week, final ranking → on-chain → payouts)
```

## Score Cycle (every N seconds)

1. **Resolve inputs**: find RECEIVED inputs past horizon → fetch feed window → resolve_ground_truth() → RESOLVED
2. **Score predictions**: find PENDING predictions with RESOLVED inputs → scoring_function() → ScoreRecord → prediction SCORED
3. **Write snapshot**: condense all scores from this cycle into one SnapshotRecord per model

## Snapshot

Per-model summary for a time period. Avoids heavy queries at checkpoint time.

```
SnapshotRecord:
    id: str
    model_id: str
    period_start: datetime
    period_end: datetime
    prediction_count: int
    result_summary: dict[str, Any]   # contract.score_type aggregated
    scored_at: datetime
```

The leaderboard also reads from snapshots — not raw scores.

## Checkpoint

Weekly aggregation of snapshots → final ranking → on-chain.

```
CheckpointRecord:
    id: str
    period_start: datetime       # since last checkpoint
    period_end: datetime
    entries: list[dict]          # ranked model entries
    meta: dict[str, Any]
    created_at: datetime
    pushed_at: datetime | None   # when pushed on-chain
    tx_hash: str | None          # on-chain reference
```

Checkpoint → payout transformation is a separate process (emissions / USDC conversion), not yet defined.

## What Changes

- `_rebuild_leaderboard` → reads snapshots instead of all scores + predictions
- New `SnapshotRecord` entity + `SnapshotRow` table
- New `CheckpointRecord` entity + `CheckpointRow` table
- Score service writes snapshot after each score cycle
- New checkpoint worker/job (weekly)
- Leaderboard built from snapshots, not raw scores

## Aggregation Callable

`CrunchContract.aggregate_snapshot` — user-customizable, default averages all numeric fields from score results:

```python
def default_aggregate_snapshot(score_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Average all numeric values across score results in the period."""
    ...

class CrunchContract:
    aggregate_snapshot: Callable = default_aggregate_snapshot
```

## Checkpoint Scheduling & API

Checkpoints run on a cron-like schedule (default: weekly, specific day+time):

```
CHECKPOINT_CRON="0 0 * * MON"     # every Monday at 00:00 UTC
```

**Status lifecycle:** `PENDING` → `SUBMITTED` → `CLAIMABLE` → `PAID`

The coordinator does NOT hold keys. The operator signs in the browser with their wallet.

Report worker endpoints:

```
GET  /reports/checkpoints                      # list all checkpoints
GET  /reports/checkpoints/latest               # latest checkpoint
GET  /reports/checkpoints/{id}/payload         # on-chain payload (rankings, amounts) for wallet signing
POST /reports/checkpoints/{id}/confirm         # FE sends {tx_hash: "0x..."} after operator signs
PATCH /reports/checkpoints/{id}/status         # update status (CLAIMABLE, PAID) from on-chain events
```

Flow:
1. Checkpoint created on schedule → PENDING
2. FE shows checkpoint, operator reviews
3. `GET payload` → FE presents for wallet signing
4. Operator signs + submits tx in browser
5. FE calls `POST confirm` with tx_hash → SUBMITTED
6. On-chain event / manual update → CLAIMABLE → PAID

## Configuration

```
SCORE_INTERVAL_SECONDS=60          # score + snapshot cadence
CHECKPOINT_CRON="0 0 * * MON"     # weekly schedule (cron syntax)
```
