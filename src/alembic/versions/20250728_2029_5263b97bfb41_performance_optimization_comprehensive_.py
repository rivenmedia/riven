"""performance_optimization_comprehensive_schema_changes

Comprehensive database schema changes for Riven performance optimizations.
This migration includes all database changes needed for:
- Show status tracking for intelligent re-indexing
- Season/episode count tracking for change detection
- Stream parsed data storage
- Performance indexes

Revision ID: 5263b97bfb41
Revises: 834cba7d26b4
Create Date: 2025-07-28 20:29:44.751887

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '5263b97bfb41'
down_revision: Union[str, None] = '834cba7d26b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add all performance optimization database changes."""

    # Get connection and inspector to check existing columns
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # === MediaItem Table Changes ===
    mediaitem_columns = [col['name'] for col in inspector.get_columns('MediaItem')]

    # Show status tracking columns for intelligent re-indexing
    if 'show_status' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('show_status', sa.String(20), nullable=True,
                                        comment="Show status: ongoing, ended, hiatus, unknown"))

    if 'last_air_date' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('last_air_date', sa.DateTime(), nullable=True,
                                        comment="Date of last aired episode"))

    if 'next_air_date' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('next_air_date', sa.DateTime(), nullable=True,
                                        comment="Date of next expected episode"))

    if 'status_last_updated' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('status_last_updated', sa.DateTime(), nullable=True,
                                        comment="When status was last updated"))

    # Season/episode count tracking for change detection
    if 'last_season_count' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('last_season_count', sa.Integer(), nullable=True, default=0,
                                        comment="Previous season count for change detection"))

    if 'last_episode_count' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('last_episode_count', sa.Integer(), nullable=True, default=0,
                                        comment="Previous episode count for change detection"))

    if 'season_episode_counts' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('season_episode_counts', sa.JSON(), nullable=True,
                                        comment="Episode counts per season: {\"1\": 10, \"2\": 12}"))

    if 'season_count' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('season_count', sa.Integer(), nullable=True, default=0,
                                        comment="Current season count"))

    if 'episode_count' not in mediaitem_columns:
        with op.batch_alter_table('MediaItem', schema=None) as batch_op:
            batch_op.add_column(sa.Column('episode_count', sa.Integer(), nullable=True, default=0,
                                        comment="Current total episode count"))

    # === Stream Table Changes ===
    stream_columns = [col['name'] for col in inspector.get_columns('Stream')]

    if 'parsed_data' not in stream_columns:
        with op.batch_alter_table('Stream', schema=None) as batch_op:
            batch_op.add_column(sa.Column('parsed_data', sa.JSON(), nullable=True,
                                        comment="Parsed torrent data from RTN"))

    # === Performance Indexes ===
    # MediaItem indexes for show status tracking
    _create_index_safe('ix_mediaitem_show_status', 'MediaItem', ['show_status'])
    _create_index_safe('ix_mediaitem_last_air_date', 'MediaItem', ['last_air_date'])
    _create_index_safe('ix_mediaitem_next_air_date', 'MediaItem', ['next_air_date'])
    _create_index_safe('ix_mediaitem_status_last_updated', 'MediaItem', ['status_last_updated'])

    # Composite indexes for efficient queries
    _create_index_safe('ix_mediaitem_type_show_status', 'MediaItem', ['type', 'show_status'])
    _create_index_safe('ix_mediaitem_show_status_next_air', 'MediaItem', ['show_status', 'next_air_date'])


def _create_index_safe(index_name: str, table_name: str, columns: list[str], unique: bool = False):
    """Create index with error handling for existing indexes."""
    try:
        op.create_index(index_name, table_name, columns, unique=unique)
    except Exception:
        # Index might already exist, ignore error
        pass


def downgrade() -> None:
    """Remove all performance optimization database changes."""

    # Get connection and inspector to check existing columns
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    # === Drop Indexes First ===
    _drop_index_safe('ix_mediaitem_show_status_next_air', 'MediaItem')
    _drop_index_safe('ix_mediaitem_type_show_status', 'MediaItem')
    _drop_index_safe('ix_mediaitem_status_last_updated', 'MediaItem')
    _drop_index_safe('ix_mediaitem_next_air_date', 'MediaItem')
    _drop_index_safe('ix_mediaitem_last_air_date', 'MediaItem')
    _drop_index_safe('ix_mediaitem_show_status', 'MediaItem')

    # === Remove MediaItem Columns ===
    mediaitem_columns = [col['name'] for col in inspector.get_columns('MediaItem')]

    with op.batch_alter_table('MediaItem', schema=None) as batch_op:
        if 'episode_count' in mediaitem_columns:
            batch_op.drop_column('episode_count')
        if 'season_count' in mediaitem_columns:
            batch_op.drop_column('season_count')
        if 'season_episode_counts' in mediaitem_columns:
            batch_op.drop_column('season_episode_counts')
        if 'last_episode_count' in mediaitem_columns:
            batch_op.drop_column('last_episode_count')
        if 'last_season_count' in mediaitem_columns:
            batch_op.drop_column('last_season_count')
        if 'status_last_updated' in mediaitem_columns:
            batch_op.drop_column('status_last_updated')
        if 'next_air_date' in mediaitem_columns:
            batch_op.drop_column('next_air_date')
        if 'last_air_date' in mediaitem_columns:
            batch_op.drop_column('last_air_date')
        if 'show_status' in mediaitem_columns:
            batch_op.drop_column('show_status')

    # === Remove Stream Columns ===
    stream_columns = [col['name'] for col in inspector.get_columns('Stream')]

    with op.batch_alter_table('Stream', schema=None) as batch_op:
        if 'parsed_data' in stream_columns:
            batch_op.drop_column('parsed_data')


def _drop_index_safe(index_name: str, table_name: str):
    """Drop index with error handling for non-existing indexes."""
    try:
        op.drop_index(index_name, table_name=table_name)
    except Exception:
        # Index might not exist, ignore error
        pass
