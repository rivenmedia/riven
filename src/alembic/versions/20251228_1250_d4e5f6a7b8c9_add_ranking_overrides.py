"""Add ranking_overrides to MediaItem

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2024-12-28 12:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add ranking_overrides column to MediaItem
    op.add_column(
        "MediaItem",
        sa.Column("ranking_overrides", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("MediaItem", "ranking_overrides")
