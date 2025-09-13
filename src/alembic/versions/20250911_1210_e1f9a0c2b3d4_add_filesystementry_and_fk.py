"""add_filesystementry_and_fk

Revision ID: e1f9a0c2b3d4
Revises: 9b3030cd23b4
Create Date: 2025-09-11 12:10:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f9a0c2b3d4"
down_revision: Union[str, None] = "8d9cc5e5f011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Get database inspector for safety checks
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    # 1) Create FilesystemEntry table (only if it doesn't exist)
    existing_tables = inspector.get_table_names()
    if "FilesystemEntry" not in existing_tables:
        op.create_table(
            "FilesystemEntry",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("path", sa.String(), nullable=False),
            sa.Column("file_size", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
            sa.Column("is_directory", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("original_filename", sa.String(), nullable=True),
            sa.Column("original_folder", sa.String(), nullable=True),
            sa.Column("download_url", sa.String(), nullable=True),
            sa.Column("unrestricted_url", sa.String(), nullable=True),
            sa.Column("provider", sa.String(), nullable=True),
            sa.Column("provider_download_id", sa.String(), nullable=True),
            sa.Column("available_in_vfs", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    
    # Create constraints and indexes only if they don't exist
    filesystem_constraints = [c["name"] for c in inspector.get_unique_constraints("FilesystemEntry")] if "FilesystemEntry" in existing_tables else []
    filesystem_indexes = [ix["name"] for ix in inspector.get_indexes("FilesystemEntry")] if "FilesystemEntry" in existing_tables else []
    
    if "uq_filesystem_entry_path" not in filesystem_constraints:
        op.create_unique_constraint("uq_filesystem_entry_path", "FilesystemEntry", ["path"])
    if "ix_filesystem_entry_path" not in filesystem_indexes:
        op.create_index("ix_filesystem_entry_path", "FilesystemEntry", ["path"], unique=False)
    if "ix_filesystem_entry_provider" not in filesystem_indexes:
        op.create_index("ix_filesystem_entry_provider", "FilesystemEntry", ["provider"], unique=False)
    if "ix_filesystem_entry_created_at" not in filesystem_indexes:
        op.create_index("ix_filesystem_entry_created_at", "FilesystemEntry", ["created_at"], unique=False)

    # 2) Add MediaItem columns (only if they don't exist)
    mediaitem_columns = [col["name"] for col in inspector.get_columns("MediaItem")]
    
    if "filesystem_entry_id" not in mediaitem_columns:
        op.add_column(
            "MediaItem",
            sa.Column("filesystem_entry_id", sa.Integer(), nullable=True),
        )
    
    if "updated" not in mediaitem_columns:
        op.add_column(
            "MediaItem",
            sa.Column("updated", sa.Boolean(), nullable=False),
        )
    
    # Create foreign key constraint only if it doesn't exist
    mediaitem_foreign_keys = [fk["name"] for fk in inspector.get_foreign_keys("MediaItem")]
    if "fk_mediaitem_filesystem_entry_id" not in mediaitem_foreign_keys:
        op.create_foreign_key(
            "fk_mediaitem_filesystem_entry_id",
            "MediaItem",
            "FilesystemEntry",
            ["filesystem_entry_id"],
            ["id"],
            ondelete=None,
        )

    # 3) Destructive data migration: purge all MediaItems to reset state
    # Note: This will remove all user media items and related subtype rows.
    # This is intentional per migration plan.
    # Only execute if tables exist and have data
    tables_to_clear = ["Subtitle", "StreamRelation", "StreamBlacklistRelation", "Episode", "Season", "Show", "Movie", "MediaItem"]
    for table in tables_to_clear:
        if table in existing_tables:
            op.execute(f'DELETE FROM "{table}";')

    # 4) Drop legacy MediaItem columns no longer used
    # Only drop columns that actually exist
    legacy_cols = [
        'symlinked', 'symlinked_at', 'symlinked_times', 'symlink_path',
        'file', 'folder', 'alternative_folder', 'update_folder', 'key'
    ]
    with op.batch_alter_table("MediaItem") as batch_op:
        for col in legacy_cols:
            if col in mediaitem_columns:
                try:
                    batch_op.drop_column(col)
                except Exception:
                    # Some backends may not support conditional drops or may have dependencies
                    pass



def downgrade() -> None:
    # Get database inspector for safety checks
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    # Check if MediaItem table exists and get its structure
    existing_tables = inspector.get_table_names()
    if "MediaItem" not in existing_tables:
        return  # Nothing to downgrade if MediaItem doesn't exist
    
    mediaitem_columns = [col["name"] for col in inspector.get_columns("MediaItem")]
    mediaitem_foreign_keys = [fk["name"] for fk in inspector.get_foreign_keys("MediaItem")]
    
    # Remove FK and column from MediaItem (only if they exist)
    with op.batch_alter_table("MediaItem") as batch_op:
        if "fk_mediaitem_filesystem_entry_id" in mediaitem_foreign_keys:
            try:
                batch_op.drop_constraint("fk_mediaitem_filesystem_entry_id", type_="foreignkey")
            except Exception:
                pass
        
        if "filesystem_entry_id" in mediaitem_columns:
            batch_op.drop_column("filesystem_entry_id")
    
    # Drop FilesystemEntry table and its constraints/indexes (only if they exist)
    if "FilesystemEntry" not in existing_tables:
        return  # Nothing to drop if FilesystemEntry doesn't exist
    
    filesystem_indexes = [ix["name"] for ix in inspector.get_indexes("FilesystemEntry")]
    filesystem_constraints = [c["name"] for c in inspector.get_unique_constraints("FilesystemEntry")]
    
    # Drop indexes only if they exist
    if "ix_filesystem_entry_created_at" in filesystem_indexes:
        op.drop_index("ix_filesystem_entry_created_at", table_name="FilesystemEntry")
    if "ix_filesystem_entry_provider" in filesystem_indexes:
        op.drop_index("ix_filesystem_entry_provider", table_name="FilesystemEntry")
    if "ix_filesystem_entry_path" in filesystem_indexes:
        op.drop_index("ix_filesystem_entry_path", table_name="FilesystemEntry")
    
    # Drop unique constraint only if it exists
    if "uq_filesystem_entry_path" in filesystem_constraints:
        try:
            op.drop_constraint("uq_filesystem_entry_path", "FilesystemEntry", type_="unique")
        except Exception:
            pass
    
    # Drop table only if it exists
    op.drop_table("FilesystemEntry")

