"""add snapshots.content_hash

Revision ID: 002
Revises: 001
Create Date: 2026-02-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("snapshots", sa.Column("content_hash", sa.String(), nullable=True))
    op.create_index("ix_snapshots_content_hash", "snapshots", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_snapshots_content_hash", table_name="snapshots")
    op.drop_column("snapshots", "content_hash")
