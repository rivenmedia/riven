"""Add PartiallyScraped state to states enum

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2024-12-28 11:38:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add PartiallyScraped to the states enum
    op.execute("ALTER TYPE states ADD VALUE IF NOT EXISTS 'PartiallyScraped'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values
    # This is a one-way migration
    pass
