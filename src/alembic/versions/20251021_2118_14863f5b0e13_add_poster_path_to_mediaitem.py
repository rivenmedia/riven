"""add_poster_path_to_mediaitem

Revision ID: 14863f5b0e13
Revises: 7e5b5cf430ff
Create Date: 2025-10-21 21:18:13.881865

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "14863f5b0e13"
down_revision: Union[str, None] = "7e5b5cf430ff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("MediaItem", schema=None) as batch_op:
        batch_op.add_column(sa.Column("poster_path", sa.String(), nullable=True))
        batch_op.create_index("ix_mediaitem_poster_path", ["poster_path"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("MediaItem", schema=None) as batch_op:
        batch_op.drop_index("ix_mediaitem_poster_path")
        batch_op.drop_column("poster_path")
