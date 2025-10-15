"""add failed attempts

Revision ID: d6c06f357feb
Revises: c99709e3648f
Create Date: 2025-02-10 07:39:51.600870

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6c06f357feb"
down_revision: Union[str, None] = "c99709e3648f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("ALTER TYPE states ADD VALUE IF NOT EXISTS 'Paused'")

    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns("MediaItem")]

    if "failed_attempts" not in columns:
        op.add_column(
            "MediaItem",
            sa.Column(
                "failed_attempts", sa.Integer(), nullable=True, server_default="0"
            ),
        )


def downgrade():
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col["name"] for col in inspector.get_columns("MediaItem")]

    if "failed_attempts" in columns:
        op.drop_column("MediaItem", "failed_attempts")

    # Note: PostgreSQL doesn't support removing enum values
    # If we need to remove the states, we'd need to:
    # 1. Create a new enum without those values
    # 2. Update the column to use the new enum
    # 3. Drop the old enum
    # This is left commented out as it's usually not worth the complexity
    """
    # Example of how to remove enum values (if needed):
    op.execute('''
        CREATE TYPE states_new AS ENUM (
            'Unknown', 'Unreleased', 'Ongoing', 'Requested', 'Indexed',
            'Scraped', 'Downloaded', 'Symlinked', 'Completed', 'PartiallyCompleted'
        )
    ''')
    op.execute('ALTER TABLE "MediaItem" ALTER COLUMN last_state TYPE states_new USING last_state::text::states_new')
    op.execute('DROP TYPE states')
    op.execute('ALTER TYPE states_new RENAME TO states')
    """
