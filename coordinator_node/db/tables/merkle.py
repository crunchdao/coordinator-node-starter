"""Merkle tree tables: cycle hashes and tree nodes for tamper evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MerkleCycleRow(SQLModel, table=True):
    """One row per score cycle. Chains to previous cycle for tamper detection."""
    __tablename__ = "merkle_cycles"

    id: str = Field(primary_key=True)
    previous_cycle_id: Optional[str] = Field(default=None, index=True)
    previous_cycle_root: Optional[str] = Field(default=None)
    snapshots_root: str
    chained_root: str = Field(index=True)
    snapshot_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now, index=True)


class MerkleNodeRow(SQLModel, table=True):
    """Nodes in a Merkle tree — leaves, intermediates, and roots."""
    __tablename__ = "merkle_nodes"

    id: str = Field(primary_key=True)
    checkpoint_id: Optional[str] = Field(
        default=None, foreign_key="checkpoints.id", index=True,
    )
    cycle_id: Optional[str] = Field(
        default=None, foreign_key="merkle_cycles.id", index=True,
    )
    level: int = Field(default=0)
    position: int = Field(default=0)
    hash: str
    left_child_id: Optional[str] = Field(default=None)
    right_child_id: Optional[str] = Field(default=None)
    snapshot_id: Optional[str] = Field(
        default=None, foreign_key="snapshots.id", index=True,
    )
    snapshot_content_hash: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
