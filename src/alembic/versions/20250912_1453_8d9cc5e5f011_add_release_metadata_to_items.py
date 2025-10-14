"""add_release_metadata_to_items

Revision ID: 8d9cc5e5f011
Revises: 9b3030cd23b4
Create Date: 2025-09-12 14:53:53.880166

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d9cc5e5f011"
down_revision: Union[str, None] = "9b3030cd23b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if release_data column already exists before adding it
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # Add release_data column to Show table (not MediaItem)
    show_columns = [col["name"] for col in inspector.get_columns("Show")]
    if "release_data" not in show_columns:
        op.add_column(
            "Show",
            sa.Column(
                "release_data",
                sa.JSON(),
                nullable=True,
                default={},
                server_default="{}",
            ),
        )


def downgrade() -> None:
    # Check if release_data column exists before dropping it
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # Drop release_data column from Show table (not MediaItem)
    show_columns = [col["name"] for col in inspector.get_columns("Show")]
    if "release_data" in show_columns:
        op.drop_column("Show", "release_data")
