"""Tests for checkpoint worker and report endpoints."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator.contracts import CrunchContract
from coordinator.entities.prediction import CheckpointRecord, SnapshotRecord
from coordinator.workers.checkpoint_worker import CheckpointService
from coordinator.workers.report_worker import (
    get_checkpoints,
    get_latest_checkpoint,
    get_checkpoint_payload,
    confirm_checkpoint,
    update_checkpoint_status,
    get_snapshots,
)


now = datetime.now(timezone.utc)


# ── In-memory repos ──


class MemSnapshotRepository:
    def __init__(self, snapshots: list[SnapshotRecord] | None = None):
        self.snapshots = list(snapshots or [])

    def save(self, record: SnapshotRecord) -> None:
        self.snapshots.append(record)

    def find(self, *, model_id=None, since=None, until=None, limit=None):
        results = list(self.snapshots)
        if model_id:
            results = [s for s in results if s.model_id == model_id]
        if since:
            results = [s for s in results if s.period_end >= since]
        if until:
            results = [s for s in results if s.period_start <= until]
        return results


class MemCheckpointRepository:
    def __init__(self, checkpoints: list[CheckpointRecord] | None = None):
        self.checkpoints = list(checkpoints or [])

    def save(self, record: CheckpointRecord) -> None:
        existing = next((c for c in self.checkpoints if c.id == record.id), None)
        if existing:
            idx = self.checkpoints.index(existing)
            self.checkpoints[idx] = record
        else:
            self.checkpoints.append(record)

    def find(self, *, status=None, limit=None):
        results = list(self.checkpoints)
        if status:
            results = [c for c in results if c.status == status]
        results.sort(key=lambda c: c.created_at, reverse=True)
        if limit:
            results = results[:limit]
        return results

    def get_latest(self):
        if not self.checkpoints:
            return None
        return sorted(self.checkpoints, key=lambda c: c.created_at, reverse=True)[0]


class MemModelRepository:
    def __init__(self):
        self.models = {}

    def fetch_all(self):
        return dict(self.models)


# ── Snapshot helpers ──


def _make_snapshot(model_id: str, value: float, count: int = 10) -> SnapshotRecord:
    return SnapshotRecord(
        id=f"SNAP_{model_id}_{now.strftime('%H%M%S')}",
        model_id=model_id,
        period_start=now - timedelta(minutes=5),
        period_end=now,
        prediction_count=count,
        result_summary={"value": value},
        created_at=now,
    )


# ── Checkpoint creation tests ──


class TestCheckpointService(unittest.TestCase):
    def test_creates_checkpoint_from_snapshots(self):
        snapshots = [
            _make_snapshot("m1", 0.8, count=100),
            _make_snapshot("m2", 0.6, count=50),
        ]
        snap_repo = MemSnapshotRepository(snapshots)
        ckpt_repo = MemCheckpointRepository()
        model_repo = MemModelRepository()

        service = CheckpointService(
            snapshot_repository=snap_repo,
            checkpoint_repository=ckpt_repo,
            model_repository=model_repo,
            contract=CrunchContract(),
        )
        checkpoint = service.create_checkpoint()

        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint.status, "PENDING")
        self.assertEqual(len(checkpoint.entries), 2)
        self.assertEqual(checkpoint.entries[0]["rank"], 1)

    def test_skips_when_no_snapshots(self):
        snap_repo = MemSnapshotRepository()
        ckpt_repo = MemCheckpointRepository()
        model_repo = MemModelRepository()

        service = CheckpointService(
            snapshot_repository=snap_repo,
            checkpoint_repository=ckpt_repo,
            model_repository=model_repo,
        )
        checkpoint = service.create_checkpoint()

        self.assertIsNone(checkpoint)
        self.assertEqual(len(ckpt_repo.checkpoints), 0)

    def test_period_starts_from_last_checkpoint(self):
        last = CheckpointRecord(
            id="CKP_old", period_start=now - timedelta(days=14),
            period_end=now - timedelta(days=7), status="PAID",
        )
        snap_repo = MemSnapshotRepository([_make_snapshot("m1", 0.9)])
        ckpt_repo = MemCheckpointRepository([last])
        model_repo = MemModelRepository()

        service = CheckpointService(
            snapshot_repository=snap_repo,
            checkpoint_repository=ckpt_repo,
            model_repository=model_repo,
        )
        checkpoint = service.create_checkpoint()

        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint.period_start, last.period_end)


# ── Report endpoint tests ──


class TestSnapshotEndpoints(unittest.TestCase):
    def test_get_snapshots(self):
        snapshots = [_make_snapshot("m1", 0.8), _make_snapshot("m2", 0.6)]
        repo = MemSnapshotRepository(snapshots)
        result = get_snapshots(repo)
        self.assertEqual(len(result), 2)
        self.assertIn("result_summary", result[0])


class TestCheckpointEndpoints(unittest.TestCase):
    def _make_checkpoint(self, status="PENDING") -> CheckpointRecord:
        return CheckpointRecord(
            id="CKP_001",
            period_start=now - timedelta(days=7),
            period_end=now,
            status=status,
            entries=[{"model_id": "m1", "rank": 1}],
            created_at=now,
        )

    def test_get_checkpoints(self):
        repo = MemCheckpointRepository([self._make_checkpoint()])
        result = get_checkpoints(repo)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "PENDING")

    def test_get_latest_checkpoint(self):
        repo = MemCheckpointRepository([self._make_checkpoint()])
        result = get_latest_checkpoint(repo)
        self.assertEqual(result["id"], "CKP_001")

    def test_get_checkpoint_payload(self):
        repo = MemCheckpointRepository([self._make_checkpoint()])
        result = get_checkpoint_payload("CKP_001", repo)
        self.assertIn("entries", result)
        self.assertEqual(len(result["entries"]), 1)

    def test_confirm_checkpoint_sets_submitted(self):
        repo = MemCheckpointRepository([self._make_checkpoint()])
        result = confirm_checkpoint("CKP_001", {"tx_hash": "0xabc"}, repo)
        self.assertEqual(result["status"], "SUBMITTED")
        self.assertEqual(result["tx_hash"], "0xabc")

    def test_confirm_rejects_non_pending(self):
        repo = MemCheckpointRepository([self._make_checkpoint(status="SUBMITTED")])
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            confirm_checkpoint("CKP_001", {"tx_hash": "0xabc"}, repo)

    def test_status_transition_submitted_to_claimable(self):
        repo = MemCheckpointRepository([self._make_checkpoint(status="SUBMITTED")])
        result = update_checkpoint_status("CKP_001", {"status": "CLAIMABLE"}, repo)
        self.assertEqual(result["status"], "CLAIMABLE")

    def test_invalid_status_transition_rejected(self):
        repo = MemCheckpointRepository([self._make_checkpoint(status="PENDING")])
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            update_checkpoint_status("CKP_001", {"status": "PAID"}, repo)


if __name__ == "__main__":
    unittest.main()
