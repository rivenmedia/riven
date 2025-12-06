"""Move episode field

Revision ID: b1345f835923
Revises: 6ad2a91a3d7f
Create Date: 2025-11-25 00:44:29.233896

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1345f835923"
down_revision: Union[str, None] = "6ad2a91a3d7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Get table names (handle case-sensitivity)
    table_names = inspector.get_table_names()
    table_names_lower = [t.lower() for t in table_names]

    # Check if Episode and Season tables exist (case-insensitive)
    has_episode_table = "episode" in table_names_lower
    has_season_table = "season" in table_names_lower

    if not has_episode_table and not has_season_table:
        # Tables don't exist yet - this is a fresh migration path
        # Just drop the number column from MediaItem if it exists
        columns = [col["name"] for col in inspector.get_columns("MediaItem")]
        if "number" in columns:
            with op.batch_alter_table("MediaItem", schema=None) as batch_op:
                batch_op.drop_column("number")
        return

    # Step 1: Add columns as nullable (only if tables exist)
    episode_columns = []
    season_columns = []

    if has_episode_table:
        episode_columns = [col["name"] for col in inspector.get_columns("Episode")]
        if "number" not in episode_columns:
            with op.batch_alter_table("Episode", schema=None) as batch_op:
                batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))

    if has_season_table:
        season_columns = [col["name"] for col in inspector.get_columns("Season")]
        if "number" not in season_columns:
            with op.batch_alter_table("Season", schema=None) as batch_op:
                batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))

    # Step 2: Migrate data from MediaItem.number to Episode.number and Season.number
    # Only do this if we have MediaItem.number AND the Episode/Season.number columns exist
    mediaitem_columns = [col["name"] for col in inspector.get_columns("MediaItem")]

    if "number" in mediaitem_columns:
        if has_episode_table and "number" in episode_columns:
            connection.execute(
                sa.text(
                    """
                    UPDATE "Episode" 
                    SET number = (
                        SELECT number 
                        FROM "MediaItem" 
                        WHERE "MediaItem".id = "Episode".id
                    )
                    WHERE "Episode".number IS NULL
                    """
                )
            )

        if has_season_table and "number" in season_columns:
            connection.execute(
                sa.text(
                    """
                    UPDATE "Season" 
                    SET number = (
                        SELECT number 
                        FROM "MediaItem" 
                        WHERE "MediaItem".id = "Season".id
                    )
                    WHERE "Season".number IS NULL
                    """
                )
            )

    # Delete invalid episodes/seasons
    if has_episode_table and "number" in episode_columns:
        connection.execute(
            sa.text(
                'DELETE FROM "Episode" WHERE number IS NULL OR number <= 0',
            )
        )

    if has_season_table and "number" in season_columns:
        connection.execute(
            sa.text(
                'DELETE FROM "Season" WHERE number IS NULL OR number <= 0',
            )
        )

    # Step 3: Alter columns to non-nullable (only if we added them)
    if has_episode_table and "number" in episode_columns:
        with op.batch_alter_table("Episode", schema=None) as batch_op:
            batch_op.alter_column("number", nullable=False)

    if has_season_table and "number" in season_columns:
        with op.batch_alter_table("Season", schema=None) as batch_op:
            batch_op.alter_column("number", nullable=False)

    # Step 4: Drop the old column from MediaItem if it exists
    if "number" in mediaitem_columns:
        with op.batch_alter_table("MediaItem", schema=None) as batch_op:
            batch_op.drop_column("number")


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Get table names (handle case-sensitivity)
    table_names = inspector.get_table_names()
    table_names_lower = [t.lower() for t in table_names]

    # Check if tables exist (case-insensitive)
    has_episode_table = "episode" in table_names_lower
    has_season_table = "season" in table_names_lower

    # Re-add MediaItem.number as nullable
    columns = [col["name"] for col in inspector.get_columns("MediaItem")]
    if "number" not in columns:
        with op.batch_alter_table("MediaItem", schema=None) as batch_op:
            batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))

    # Migrate data back from Episode and Season to MediaItem (only if tables exist)
    if has_episode_table:
        connection.execute(
            sa.text(
                """
                UPDATE MediaItem 
                SET number = (
                    SELECT number 
                    FROM Episode 
                    WHERE Episode.id = MediaItem.id
                )
                WHERE MediaItem.id IN (SELECT id FROM Episode)
                """
            )
        )

    if has_season_table:
        connection.execute(
            sa.text(
                """
                UPDATE MediaItem 
                SET number = (
                    SELECT number 
                    FROM Season 
                    WHERE Season.id = MediaItem.id
                )
                WHERE MediaItem.id IN (SELECT id FROM Season)
                """
            )
        )

    # Drop the child table columns (only if tables exist)
    if has_season_table:
        columns = [col["name"] for col in inspector.get_columns("Season")]
        if "number" in columns:
            with op.batch_alter_table("Season", schema=None) as batch_op:
                batch_op.drop_column("number")

    if has_episode_table:
        columns = [col["name"] for col in inspector.get_columns("Episode")]
        if "number" in columns:
            with op.batch_alter_table("Episode", schema=None) as batch_op:
                batch_op.drop_column("number")
