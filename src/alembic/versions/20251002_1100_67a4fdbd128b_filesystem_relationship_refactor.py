"""Filesystem relationship refactor

Revision ID: 67a4fdbd128b
Revises: e1f9a0c2b3d4
Create Date: 2025-10-02 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67a4fdbd128b'
down_revision: Union[str, None] = 'e1f9a0c2b3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Flip the relationship between MediaItem and FilesystemEntry.

    Before: MediaItem.filesystem_entry_id -> FilesystemEntry.id (many-to-one, FK on MediaItem)
    After: FilesystemEntry.media_item_id -> MediaItem.id (many-to-one, FK on FilesystemEntry)

    This makes MediaItem the parent and FilesystemEntry the child, allowing:
    - Proper use of cascade="all, delete-orphan" for automatic cleanup
    - Future expansion: one MediaItem can have multiple FilesystemEntries (different locations/profiles)
    """
    from alembic import context
    conn = context.get_bind()
    inspector = sa.inspect(conn)

    # Step 1: Add media_item_id column to FilesystemEntry if it doesn't exist
    columns = [c['name'] for c in inspector.get_columns('FilesystemEntry')]
    if 'media_item_id' not in columns:
        op.add_column('FilesystemEntry', sa.Column('media_item_id', sa.Integer(), nullable=True))

    # Step 2: Copy data from MediaItem.filesystem_entry_id to FilesystemEntry.media_item_id
    # Only if filesystem_entry_id column still exists
    mediaitem_columns = [c['name'] for c in inspector.get_columns('MediaItem')]
    if 'filesystem_entry_id' in mediaitem_columns:
        op.execute("""
            UPDATE "FilesystemEntry" AS fe
            SET media_item_id = mi.id
            FROM "MediaItem" AS mi
            WHERE mi.filesystem_entry_id = fe.id
        """)

        # Step 3: Drop the old FK constraint and column from MediaItem
        # Check if constraint exists before dropping
        constraints = [c['name'] for c in inspector.get_foreign_keys('MediaItem')]
        if 'fk_mediaitem_filesystem_entry_id' in constraints:
            op.drop_constraint("fk_mediaitem_filesystem_entry_id", "MediaItem", type_="foreignkey")

        # Drop the column
        op.drop_column("MediaItem", "filesystem_entry_id")

    # Step 4: Add FK constraint on FilesystemEntry.media_item_id with CASCADE delete
    # Check if constraint doesn't already exist
    fs_constraints = [c['name'] for c in inspector.get_foreign_keys('FilesystemEntry')]
    if 'fk_filesystementry_media_item_id' not in fs_constraints:
        op.create_foreign_key(
            "fk_filesystementry_media_item_id",
            "FilesystemEntry",
            "MediaItem",
            ["media_item_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # Step 5: Add index on media_item_id for performance
    # Check if index doesn't already exist
    indexes = [idx['name'] for idx in inspector.get_indexes('FilesystemEntry')]
    if 'ix_filesystementry_media_item_id' not in indexes:
        op.create_index(
            "ix_filesystementry_media_item_id",
            "FilesystemEntry",
            ["media_item_id"]
        )

    # Step 6: Drop original_folder column from FilesystemEntry (no longer used)
    fs_columns = [c['name'] for c in inspector.get_columns('FilesystemEntry')]
    if 'original_folder' in fs_columns:
        with op.batch_alter_table("FilesystemEntry") as batch_op:
            batch_op.drop_column("original_folder")


def downgrade() -> None:
    """
    Revert the relationship flip.
    
    WARNING: This downgrade will fail if any MediaItem has multiple FilesystemEntries,
    as the old schema only supports one FilesystemEntry per MediaItem.
    """
    from alembic import context
    conn = context.get_bind()
    inspector = sa.inspect(conn)

    # Step 1: Re-add original_folder column to FilesystemEntry
    fs_columns = [c['name'] for c in inspector.get_columns('FilesystemEntry')]
    if 'original_folder' not in fs_columns:
        op.add_column('FilesystemEntry', sa.Column('original_folder', sa.String(), nullable=True))

    # Step 2: Add filesystem_entry_id column back to MediaItem
    mediaitem_columns = [c['name'] for c in inspector.get_columns('MediaItem')]
    if 'filesystem_entry_id' not in mediaitem_columns:
        op.add_column('MediaItem', sa.Column('filesystem_entry_id', sa.Integer(), nullable=True))
    
    # Step 3: Copy data back (only the first FilesystemEntry for each MediaItem)
    # This will lose data if a MediaItem has multiple FilesystemEntries!
    op.execute("""
        UPDATE "MediaItem" AS mi
        SET filesystem_entry_id = (
            SELECT fe.id
            FROM "FilesystemEntry" AS fe
            WHERE fe.media_item_id = mi.id
            LIMIT 1
        )
    """)

    # Step 4: Drop FK constraint and index from FilesystemEntry
    indexes = [idx['name'] for idx in inspector.get_indexes('FilesystemEntry')]
    if 'ix_filesystementry_media_item_id' in indexes:
        op.drop_index("ix_filesystementry_media_item_id", table_name="FilesystemEntry")

    fs_constraints = [c['name'] for c in inspector.get_foreign_keys('FilesystemEntry')]
    if 'fk_filesystementry_media_item_id' in fs_constraints:
        op.drop_constraint("fk_filesystementry_media_item_id", "FilesystemEntry", type_="foreignkey")

    # Step 5: Drop media_item_id column from FilesystemEntry
    columns = [c['name'] for c in inspector.get_columns('FilesystemEntry')]
    if 'media_item_id' in columns:
        with op.batch_alter_table("FilesystemEntry") as batch_op:
            batch_op.drop_column("media_item_id")

    # Step 6: Re-add FK constraint on MediaItem.filesystem_entry_id with SET NULL
    constraints = [c['name'] for c in inspector.get_foreign_keys('MediaItem')]
    if 'fk_mediaitem_filesystem_entry_id' not in constraints:
        op.create_foreign_key(
            "fk_mediaitem_filesystem_entry_id",
            "MediaItem",
            "FilesystemEntry",
            ["filesystem_entry_id"],
            ["id"],
            ondelete="SET NULL"
        )

