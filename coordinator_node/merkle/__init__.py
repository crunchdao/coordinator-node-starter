"""Merkle tree tamper evidence for snapshots and checkpoints."""

from coordinator_node.merkle.hasher import canonical_snapshot_hash, sha256_concat
from coordinator_node.merkle.service import MerkleService
from coordinator_node.merkle.tree import (
    MerkleNode,
    MerkleProof,
    ProofStep,
    build_merkle_tree,
    generate_proof,
    get_root,
    verify_proof,
)

__all__ = [
    "MerkleNode",
    "MerkleProof",
    "MerkleService",
    "ProofStep",
    "build_merkle_tree",
    "canonical_snapshot_hash",
    "generate_proof",
    "get_root",
    "sha256_concat",
    "verify_proof",
]
