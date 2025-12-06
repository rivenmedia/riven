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
    # Step 1: Add columns as nullable
    with op.batch_alter_table("Episode", schema=None) as batch_op:
        batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))

    with op.batch_alter_table("Season", schema=None) as batch_op:
        batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))

    # Step 2: Migrate data from MediaItem.number to Episode.number and Season.number
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE Episode 
            SET number = (
                SELECT number 
                FROM MediaItem 
                WHERE MediaItem.id = Episode.id
            )
            WHERE Episode.number IS NULL
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE Season 
            SET number = (
                SELECT number 
                FROM MediaItem 
                WHERE MediaItem.id = Season.id
            )
            WHERE Season.number IS NULL
            """
        )
    )

    # Delete invalid episodes/seasons
    connection.execute(
        sa.text(
            "DELETE FROM Episode WHERE number IS NULL OR number <= 0",
        )
    )

    connection.execute(
        sa.text(
            "DELETE FROM Season WHERE number IS NULL OR number <= 0",
        )
    )

    # Step 3: Alter columns to non-nullable
    with op.batch_alter_table("Episode", schema=None) as batch_op:
        batch_op.alter_column("number", nullable=False)

    with op.batch_alter_table("Season", schema=None) as batch_op:
        batch_op.alter_column("number", nullable=False)

    # Step 4: Drop the old column
    with op.batch_alter_table("MediaItem", schema=None) as batch_op:
        batch_op.drop_column("number")


def downgrade() -> None:
    # Re-add MediaItem.number as nullable
    with op.batch_alter_table("MediaItem", schema=None) as batch_op:
        batch_op.add_column(sa.Column("number", sa.Integer(), nullable=True))

    # Migrate data back from Episode and Season to MediaItem
    connection = op.get_bind()
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

    # Drop the child table columns
    with op.batch_alter_table("Season", schema=None) as batch_op:
        batch_op.drop_column("number")

    with op.batch_alter_table("Episode", schema=None) as batch_op:
        batch_op.drop_column("number")
