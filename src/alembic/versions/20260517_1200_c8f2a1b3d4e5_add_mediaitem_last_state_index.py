"""Add index on MediaItem.last_state for stats and pipeline queries

Revision ID: c8f2a1b3d4e5
Revises: b1345f835923
Create Date: 2026-05-17 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c8f2a1b3d4e5"
down_revision: Union[str, None] = "b1345f835923"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_mediaitem_last_state",
        "MediaItem",
        ["last_state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mediaitem_last_state", table_name="MediaItem")
