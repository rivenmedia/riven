"""add_cascade_ondelete

Revision ID: 9b3030cd23b4
Revises: add_resolution_to_stream
Create Date: 2025-09-06 20:37:08.871075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b3030cd23b4'
down_revision: Union[str, None] = 'add_resolution_to_stream'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Movie/Show/Season/Episode child FKs to MediaItem
    op.drop_constraint("Movie_id_fkey", "Movie", type_="foreignkey")
    op.create_foreign_key(
        "Movie_id_fkey",
        "Movie", "MediaItem",
        ["id"], ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("Show_id_fkey", "Show", type_="foreignkey")
    op.create_foreign_key(
        "Show_id_fkey",
        "Show", "MediaItem",
        ["id"], ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("Season_id_fkey", "Season", type_="foreignkey")
    op.create_foreign_key(
        "Season_id_fkey",
        "Season", "MediaItem",
        ["id"], ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("Episode_id_fkey", "Episode", type_="foreignkey")
    op.create_foreign_key(
        "Episode_id_fkey",
        "Episode", "MediaItem",
        ["id"], ["id"],
        ondelete="CASCADE",
    )

    # Parent chain (hierarchy)
    op.drop_constraint("Season_parent_id_fkey", "Season", type_="foreignkey")
    op.create_foreign_key(
        "Season_parent_id_fkey",
        "Season", "Show",
        ["parent_id"], ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("Episode_parent_id_fkey", "Episode", type_="foreignkey")
    op.create_foreign_key(
        "Episode_parent_id_fkey",
        "Episode", "Season",
        ["parent_id"], ["id"],
        ondelete="CASCADE",
    )

    # Subtitle if needed (adjust names)
    op.drop_constraint("Subtitle_parent_id_fkey", "Subtitle", type_="foreignkey")
    op.create_foreign_key(
        "Subtitle_parent_id_fkey",
        "Subtitle", "MediaItem",
        ["parent_id"], ["id"],
        ondelete="CASCADE",
    )

def downgrade():
    pass