# Merkle Tree Tamper Evidence for Snapshots & Checkpoints

## Overview

Safeguard against coordinator cheating by building Merkle trees over snapshots and checkpoints. Every score cycle commits snapshot hashes into a chained hash structure. At checkpoint time, cycle roots become leaves of a checkpoint-level Merkle tree. The root is stored on the checkpoint record for future external anchoring (Irys/IPFS/on-chain).

## Threat Model

1. **Retroactive tampering** — coordinator rewrites historical snapshots/scores
2. **Selective omission** — coordinator drops models' snapshots from checkpoints
3. **Full auditability** — external parties can verify checkpoint rankings are faithful
4. **Chain integrity** — each cycle chains to the previous, so any mutation breaks the chain forward

## Data Model

### SnapshotRow (modified)
- `content_hash: str | None` — SHA-256 of canonical snapshot content

### CheckpointRow (modified)
- `merkle_root: str | None` — root hash of checkpoint Merkle tree

### MerkleCycleRow (new)
```
id: str                        # "CYC_{timestamp}"
previous_cycle_id: str | None
previous_cycle_root: str | None
snapshots_root: str            # mini-tree root over this cycle's snapshots
chained_root: str              # SHA-256(previous_cycle_root + snapshots_root)
snapshot_count: int
created_at: datetime
```

### MerkleNodeRow (new)
```
id: str                        # "MRK_{parent_id}_{index}"
checkpoint_id: str | None      # FK → checkpoints.id
cycle_id: str | None           # FK → merkle_cycles.id
level: int                     # 0 = leaf, 1+ = intermediate
position: int                  # left-to-right at this level
hash: str                      # hex SHA-256
left_child_id: str | None
right_child_id: str | None
snapshot_id: str | None         # FK → snapshots.id (leaves only)
snapshot_content_hash: str | None  # copy at tree-build time
created_at: datetime
```

## Canonical Hashing

```python
payload = {
    "model_id": snapshot.model_id,
    "period_start": snapshot.period_start.isoformat(),
    "period_end": snapshot.period_end.isoformat(),
    "prediction_count": snapshot.prediction_count,
    "result_summary": snapshot.result_summary,
}
raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
hash = sha256(raw.encode("utf-8")).hexdigest()
```

## Architecture

### Score Cycle (every N seconds)
After `_write_snapshots()`:
1. Compute `content_hash` for each snapshot
2. Build mini Merkle tree (leaves sorted by `model_id`)
3. Chain: `chained_root = SHA-256(previous_cycle_root + snapshots_root)`
4. Save `MerkleCycleRow` + `MerkleNodeRow`s atomically with snapshots

### Checkpoint (weekly)
During `create_checkpoint()`:
1. Gather all `MerkleCycleRow`s since last checkpoint
2. Use `chained_root` values as leaves
3. Build checkpoint Merkle tree
4. Store `merkle_root` on `CheckpointRow`

### Proof Generation
`get_merkle_proof(snapshot_id)` returns:
```
MerkleProof:
    snapshot_id: str
    snapshot_content_hash: str
    cycle_id: str
    cycle_root: str
    checkpoint_id: str | None
    merkle_root: str | None
    path: list[{hash: str, position: "left" | "right"}]
```

## API Endpoints (public, no auth)

```
GET /reports/merkle/cycles              # list recent cycles (paginated)
GET /reports/merkle/cycles/{id}         # single cycle with chained_root
GET /reports/merkle/proof?snapshot_id=X  # full inclusion proof
```

## File Changes

### New files
- `coordinator_node/merkle/__init__.py`
- `coordinator_node/merkle/hasher.py`
- `coordinator_node/merkle/tree.py`
- `coordinator_node/merkle/service.py`
- `coordinator_node/db/tables/merkle.py`
- `scripts/verify_merkle.py`
- `tests/test_merkle.py`

### Modified files
- `coordinator_node/db/tables/pipeline.py` — `content_hash` on SnapshotRow, `merkle_root` on CheckpointRow
- `coordinator_node/db/tables/__init__.py` — export new tables
- `coordinator_node/db/repositories.py` — new repositories
- `coordinator_node/services/score.py` — call `MerkleService.commit_cycle()`
- `coordinator_node/workers/checkpoint_worker.py` — call `MerkleService.commit_checkpoint()`
- `coordinator_node/workers/report_worker.py` — new endpoints

## Configuration

Always-on. No config flags. Cheap (few SHA-256s per cycle) and only valuable if running from the start.

## Future Work

- Irys/IPFS publishing of roots
- On-chain root anchoring (embed in checkpoint tx payload)
- Standalone `verify_merkle.py` for crunchers
