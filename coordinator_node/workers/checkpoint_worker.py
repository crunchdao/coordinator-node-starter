"""Checkpoint worker: periodically aggregates snapshots into checkpoints."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from coordinator_node.config_loader import load_config
from coordinator_node.crunch_config import CrunchConfig
from coordinator_node.db import (
    DBCheckpointRepository,
    DBMerkleCycleRepository,
    DBMerkleNodeRepository,
    DBModelRepository,
    DBSnapshotRepository,
    create_session,
)
from coordinator_node.merkle.service import MerkleService
from coordinator_node.entities.prediction import CheckpointRecord, CheckpointStatus


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        force=True,
    )


class CheckpointService:
    def __init__(
        self,
        snapshot_repository: DBSnapshotRepository,
        checkpoint_repository: DBCheckpointRepository,
        model_repository: DBModelRepository,
        contract: CrunchConfig | None = None,
        interval_seconds: int = 7 * 24 * 3600,  # weekly
        merkle_service: MerkleService | None = None,
    ):
        self.snapshot_repository = snapshot_repository
        self.checkpoint_repository = checkpoint_repository
        self.model_repository = model_repository
        self.contract = contract or CrunchConfig()
        self.interval_seconds = interval_seconds
        self.merkle_service = merkle_service
        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        self.logger.info("checkpoint worker started (interval=%ds)", self.interval_seconds)
        while not self.stop_event.is_set():
            try:
                self.create_checkpoint()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.logger.exception("checkpoint error: %s", exc)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                pass

    def create_checkpoint(self) -> CheckpointRecord | None:
        now = datetime.now(timezone.utc)

        # Determine period start: end of last checkpoint, or beginning of time
        last = self.checkpoint_repository.get_latest()
        period_start = last.period_end if last else now - timedelta(seconds=self.interval_seconds)

        # Get all snapshots in this period
        snapshots = self.snapshot_repository.find(since=period_start, until=now)
        if not snapshots:
            self.logger.info("No snapshots since %s, skipping checkpoint", period_start.isoformat())
            return None

        models = self.model_repository.fetch_all()
        aggregation = self.contract.aggregation

        # Aggregate snapshots per model
        by_model: dict[str, list] = {}
        for snap in snapshots:
            by_model.setdefault(snap.model_id, []).append(snap)

        ranked_entries: list[dict[str, Any]] = []
        for model_id, model_snapshots in by_model.items():
            # Weighted average by prediction count
            total_preds = sum(s.prediction_count for s in model_snapshots)
            if total_preds == 0:
                continue

            summary: dict[str, float] = {}
            for snap in model_snapshots:
                weight = snap.prediction_count / total_preds
                for key, value in snap.result_summary.items():
                    if isinstance(value, (int, float)):
                        summary[key] = summary.get(key, 0.0) + float(value) * weight

            model = models.get(model_id)
            ranked_entries.append({
                "model_id": model_id,
                "model_name": model.name if model else None,
                "cruncher_name": model.player_name if model else None,
                "prediction_count": total_preds,
                "snapshot_count": len(model_snapshots),
                "result_summary": summary,
            })

        # Rank by the aggregation ranking key
        ranking_key = aggregation.ranking_key
        reverse = aggregation.ranking_direction == "desc"
        ranked_entries.sort(
            key=lambda e: float(e.get("result_summary", {}).get(ranking_key, 0)),
            reverse=reverse,
        )
        for idx, entry in enumerate(ranked_entries, start=1):
            entry["rank"] = idx

        # Build emission checkpoint → protocol format for on-chain submission
        emission = self.contract.build_emission(
            ranked_entries,
            crunch_pubkey=self.contract.crunch_pubkey,
            compute_provider=self.contract.compute_provider,
            data_provider=self.contract.data_provider,
        )

        checkpoint = CheckpointRecord(
            id=f"CKP_{now.strftime('%Y%m%d_%H%M%S')}",
            period_start=period_start,
            period_end=now,
            status=CheckpointStatus.PENDING,
            entries=[emission],
            meta={
                "snapshot_count": len(snapshots),
                "model_count": len(ranked_entries),
                "ranking": ranked_entries,
            },
            created_at=now,
        )

        self.checkpoint_repository.save(checkpoint)

        # Merkle tamper evidence: build tree over cycle roots
        if self.merkle_service:
            try:
                merkle_root = self.merkle_service.commit_checkpoint(
                    checkpoint_id=checkpoint.id,
                    period_start=period_start,
                    period_end=now,
                    now=now,
                )
                if merkle_root:
                    self.checkpoint_repository.update_merkle_root(checkpoint.id, merkle_root)
                    self.logger.info("Checkpoint %s merkle_root=%s", checkpoint.id, merkle_root[:16])
            except Exception as exc:
                self.logger.warning("Merkle checkpoint commit failed: %s", exc)

        self.logger.info(
            "Created checkpoint %s: %d models, %d snapshots, period %s → %s",
            checkpoint.id, len(ranked_entries), len(snapshots),
            period_start.isoformat(), now.isoformat(),
        )
        return checkpoint

    async def shutdown(self) -> None:
        self.stop_event.set()


def build_service() -> CheckpointService:
    session = create_session()
    interval = int(os.getenv("CHECKPOINT_INTERVAL_SECONDS", str(7 * 24 * 3600)))

    contract = load_config()

    # Env var overrides for on-chain identifiers (backward compat)
    crunch_pubkey = os.getenv("CRUNCH_PUBKEY", "")
    compute_provider = os.getenv("COMPUTE_PROVIDER_PUBKEY")
    data_provider = os.getenv("DATA_PROVIDER_PUBKEY")

    if crunch_pubkey:
        contract.crunch_pubkey = crunch_pubkey
    if compute_provider:
        contract.compute_provider = compute_provider
    if data_provider:
        contract.data_provider = data_provider

    merkle_service = MerkleService(
        merkle_cycle_repository=DBMerkleCycleRepository(session),
        merkle_node_repository=DBMerkleNodeRepository(session),
    )

    return CheckpointService(
        snapshot_repository=DBSnapshotRepository(session),
        checkpoint_repository=DBCheckpointRepository(session),
        model_repository=DBModelRepository(session),
        contract=contract,
        interval_seconds=interval,
        merkle_service=merkle_service,
    )


async def main() -> None:
    configure_logging()
    logging.getLogger(__name__).info("coordinator checkpoint worker bootstrap")
    service = build_service()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
