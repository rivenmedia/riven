"""Add resolution column to Stream table

Revision ID: add_resolution_to_stream
Revises: 834cba7d26b4
Create Date: 2025-01-05 12:00:00.000000

"""
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision = "add_resolution_to_stream"
down_revision = "834cba7d26b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # Add 'resolution' column to 'Stream' if it doesn't exist
    stream_columns = [col["name"] for col in inspector.get_columns("Stream")]
    if "resolution" not in stream_columns:
        op.add_column("Stream", sa.Column("resolution", sa.String(), nullable=True))

    # Create index on 'resolution' if it doesn't exist
    stream_indexes = [ix["name"] for ix in inspector.get_indexes("Stream")]
    if "ix_stream_resolution" not in stream_indexes:
        op.create_index("ix_stream_resolution", "Stream", ["resolution"], unique=False)

    # Add 'absolute_number' column to 'Episode' if it doesn't exist
    episode_columns = [col["name"] for col in inspector.get_columns("Episode")]
    if "absolute_number" not in episode_columns:
        op.add_column("Episode", sa.Column("absolute_number", sa.Integer(), nullable=True))

    # Create index on 'absolute_number' if it doesn't exist
    episode_indexes = [ix["name"] for ix in inspector.get_indexes("Episode")]
    if "ix_episode_absolute_number" not in episode_indexes:
        op.create_index("ix_episode_absolute_number", "Episode", ["absolute_number"], unique=False)

def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # Drop index on 'resolution' if it exists
    stream_indexes = [ix["name"] for ix in inspector.get_indexes("Stream")]
    if "ix_stream_resolution" in stream_indexes:
        op.drop_index("ix_stream_resolution", table_name="Stream")

    # Drop 'resolution' column from 'Stream' if it exists
    stream_columns = [col["name"] for col in inspector.get_columns("Stream")]
    if "resolution" in stream_columns:
        op.drop_column("Stream", "resolution")

    # Drop index on 'absolute_number' if it exists
    episode_indexes = [ix["name"] for ix in inspector.get_indexes("Episode")]
    if "ix_episode_absolute_number" in episode_indexes:
        op.drop_index("ix_episode_absolute_number", table_name="Episode")

    # Drop 'absolute_number' column from 'Episode' if it exists
    episode_columns = [col["name"] for col in inspector.get_columns("Episode")]
    if "absolute_number" in episode_columns:
        op.drop_column("Episode", "absolute_number")