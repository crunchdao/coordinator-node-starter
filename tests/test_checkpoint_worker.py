"""Tests for checkpoint worker, prize distribution, and report endpoints."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator.contracts import (
    CrunchContract, default_distribute_prizes, usdc_to_micro,
)
from coordinator.entities.prediction import (
    CheckpointRecord, CheckpointStatus, SnapshotRecord,
)
from coordinator.workers.checkpoint_worker import CheckpointService


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


# ── USDC micro-unit conversion ──


class TestUsdcConversion(unittest.TestCase):
    def test_usdc_to_micro(self):
        self.assertEqual(usdc_to_micro(1.0), 1_000_000)
        self.assertEqual(usdc_to_micro(338.98), 338_980_000)
        self.assertEqual(usdc_to_micro(0.0), 0)
        self.assertEqual(usdc_to_micro(0.000001), 1)


# ── Prize distribution ──


class TestPrizeDistribution(unittest.TestCase):
    def test_default_tiers_1st_35pct(self):
        entries = [{"model_id": "m1", "rank": 1}]
        result = default_distribute_prizes(entries, 1000.0)
        self.assertEqual(result[0]["model"], "m1")
        self.assertEqual(result[0]["prize"], usdc_to_micro(350.0))

    def test_default_tiers_2nd_through_5th_10pct(self):
        entries = [{"model_id": f"m{i}", "rank": i} for i in range(1, 6)]
        result = default_distribute_prizes(entries, 1000.0)
        for i in range(1, 5):  # ranks 2-5
            self.assertEqual(result[i]["prize"], usdc_to_micro(100.0))

    def test_default_tiers_6th_through_10th_5pct(self):
        entries = [{"model_id": f"m{i}", "rank": i} for i in range(1, 11)]
        result = default_distribute_prizes(entries, 1000.0)
        for i in range(5, 10):  # ranks 6-10
            self.assertEqual(result[i]["prize"], usdc_to_micro(50.0))

    def test_unranked_models_get_zero(self):
        entries = [{"model_id": f"m{i}", "rank": i} for i in range(1, 15)]
        result = default_distribute_prizes(entries, 1000.0)
        for i in range(10, 14):  # ranks 11-14
            self.assertEqual(result[i]["prize"], 0)

    def test_full_pool_allocation_10_models(self):
        entries = [{"model_id": f"m{i}", "rank": i} for i in range(1, 11)]
        result = default_distribute_prizes(entries, 1000.0)
        total = sum(e["prize"] for e in result)
        # 35 + 4*10 + 5*5 = 100% of 1000 USDC
        self.assertEqual(total, usdc_to_micro(1000.0))

    def test_protocol_format(self):
        entries = [{"model_id": "11680", "rank": 1}]
        result = default_distribute_prizes(entries, 338.98)
        # 35% of 338.98 = 118.643 USDC
        self.assertEqual(result[0]["model"], "11680")
        self.assertEqual(result[0]["prize"], usdc_to_micro(338.98 * 0.35))
        self.assertIsInstance(result[0]["model"], str)
        self.assertIsInstance(result[0]["prize"], int)


# ── Checkpoint creation ──


class TestCheckpointService(unittest.TestCase):
    def test_creates_checkpoint_with_protocol_entries(self):
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
            contract=CrunchContract(pool_usdc=1000.0),
        )
        checkpoint = service.create_checkpoint()

        self.assertIsNotNone(checkpoint)
        self.assertEqual(checkpoint.status, CheckpointStatus.PENDING)
        self.assertEqual(len(checkpoint.entries), 2)

        # Protocol format: {"model": str, "prize": int}
        self.assertIn("model", checkpoint.entries[0])
        self.assertIn("prize", checkpoint.entries[0])
        self.assertIsInstance(checkpoint.entries[0]["prize"], int)

        # 1st place gets 35% of 1000 USDC
        self.assertEqual(checkpoint.entries[0]["prize"], usdc_to_micro(350.0))
        # 2nd place gets 10% of 1000 USDC
        self.assertEqual(checkpoint.entries[1]["prize"], usdc_to_micro(100.0))

        # Ranking details in meta
        self.assertIn("ranking", checkpoint.meta)
        self.assertEqual(checkpoint.meta["ranking"][0]["rank"], 1)

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
            period_end=now - timedelta(days=7), status=CheckpointStatus.PAID,
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
        from coordinator.workers.report_worker import get_snapshots

        snapshots = [_make_snapshot("m1", 0.8), _make_snapshot("m2", 0.6)]
        repo = MemSnapshotRepository(snapshots)
        result = get_snapshots(repo)
        self.assertEqual(len(result), 2)
        self.assertIn("result_summary", result[0])


class TestCheckpointEndpoints(unittest.TestCase):
    def _make_checkpoint(self, status=CheckpointStatus.PENDING) -> CheckpointRecord:
        return CheckpointRecord(
            id="CKP_001",
            period_start=now - timedelta(days=7),
            period_end=now,
            status=status,
            entries=[{"model": "m1", "prize": 350_000_000}],
            created_at=now,
        )

    def test_get_checkpoints(self):
        from coordinator.workers.report_worker import get_checkpoints

        repo = MemCheckpointRepository([self._make_checkpoint()])
        result = get_checkpoints(repo)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], CheckpointStatus.PENDING)

    def test_get_latest_checkpoint(self):
        from coordinator.workers.report_worker import get_latest_checkpoint

        repo = MemCheckpointRepository([self._make_checkpoint()])
        result = get_latest_checkpoint(repo)
        self.assertEqual(result["id"], "CKP_001")

    def test_get_checkpoint_payload(self):
        from coordinator.workers.report_worker import get_checkpoint_payload

        repo = MemCheckpointRepository([self._make_checkpoint()])
        result = get_checkpoint_payload("CKP_001", repo)
        self.assertIn("entries", result)
        self.assertEqual(result["entries"][0]["model"], "m1")
        self.assertEqual(result["entries"][0]["prize"], 350_000_000)

    def test_confirm_checkpoint_sets_submitted(self):
        from coordinator.workers.report_worker import confirm_checkpoint

        repo = MemCheckpointRepository([self._make_checkpoint()])
        result = confirm_checkpoint("CKP_001", {"tx_hash": "0xabc"}, repo)
        self.assertEqual(result["status"], CheckpointStatus.SUBMITTED)
        self.assertEqual(result["tx_hash"], "0xabc")

    def test_confirm_rejects_non_pending(self):
        from coordinator.workers.report_worker import confirm_checkpoint
        from fastapi import HTTPException

        repo = MemCheckpointRepository([self._make_checkpoint(status=CheckpointStatus.SUBMITTED)])
        with self.assertRaises(HTTPException):
            confirm_checkpoint("CKP_001", {"tx_hash": "0xabc"}, repo)

    def test_status_transition_submitted_to_claimable(self):
        from coordinator.workers.report_worker import update_checkpoint_status

        repo = MemCheckpointRepository([self._make_checkpoint(status=CheckpointStatus.SUBMITTED)])
        result = update_checkpoint_status("CKP_001", {"status": "CLAIMABLE"}, repo)
        self.assertEqual(result["status"], CheckpointStatus.CLAIMABLE)

    def test_invalid_status_transition_rejected(self):
        from coordinator.workers.report_worker import update_checkpoint_status
        from fastapi import HTTPException

        repo = MemCheckpointRepository([self._make_checkpoint(status=CheckpointStatus.PENDING)])
        with self.assertRaises(HTTPException):
            update_checkpoint_status("CKP_001", {"status": "PAID"}, repo)


if __name__ == "__main__":
    unittest.main()
