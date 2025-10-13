"""add_tvdb_status_to_show

Revision ID: b2c3d4e5f8g9
Revises: a1b2c3d4e5f7
Create Date: 2025-10-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f8g9"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if tvdb_status column already exists before adding it
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    # Add tvdb_status column to Show table
    show_columns = [col["name"] for col in inspector.get_columns("Show")]
    if "tvdb_status" not in show_columns:
        op.add_column("Show", sa.Column("tvdb_status", sa.String(), nullable=True))


def downgrade() -> None:
    # Check if tvdb_status column exists before dropping it
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    # Drop tvdb_status column from Show table
    show_columns = [col["name"] for col in inspector.get_columns("Show")]
    if "tvdb_status" in show_columns:
        op.drop_column("Show", "tvdb_status")

