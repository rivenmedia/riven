"""add_stream_pending_record

Add StreamPendingRecord table to track when streams enter pending state for dead torrent detection.

Revision ID: add_stream_pending_001
Revises: 4f327e05c40f
Create Date: 2025-11-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_stream_pending_001"
down_revision: Union[str, None] = "4f327e05c40f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create StreamPendingRecord table for tracking pending stream timestamps."""
    op.create_table(
        "StreamPendingRecord",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("media_item_id", sa.Integer(), nullable=False),
        sa.Column("stream_infohash", sa.String(), nullable=False),
        sa.Column("pending_since", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["media_item_id"], ["MediaItem.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_stream_pending_item_infohash",
        "StreamPendingRecord",
        ["media_item_id", "stream_infohash"],
        unique=False,
    )


def downgrade() -> None:
    """Drop StreamPendingRecord table."""
    op.drop_index("ix_stream_pending_item_infohash", table_name="StreamPendingRecord")
    op.drop_table("StreamPendingRecord")
