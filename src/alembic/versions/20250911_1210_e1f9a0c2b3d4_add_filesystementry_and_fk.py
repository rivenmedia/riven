"""add_filesystementry_and_fk

Revision ID: e1f9a0c2b3d4
Revises: 9b3030cd23b4
Create Date: 2025-09-11 12:10:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f9a0c2b3d4"
down_revision: Union[str, None] = "9b3030cd23b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Create FilesystemEntry table
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
    op.create_unique_constraint("uq_filesystem_entry_path", "FilesystemEntry", ["path"])
    op.create_index("ix_filesystem_entry_path", "FilesystemEntry", ["path"], unique=False)
    op.create_index("ix_filesystem_entry_provider", "FilesystemEntry", ["provider"], unique=False)
    op.create_index("ix_filesystem_entry_created_at", "FilesystemEntry", ["created_at"], unique=False)

    # 2) Add MediaItem.filesystem_entry_id (nullable FK)
    op.add_column(
        "MediaItem",
        sa.Column("filesystem_entry_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "MediaItem",
        sa.Column("updated", sa.Boolean(), nullable=False),

    )
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
    op.execute('DELETE FROM "Subtitle";')
    op.execute('DELETE FROM "StreamRelation";')
    op.execute('DELETE FROM "StreamBlacklistRelation";')
    op.execute('DELETE FROM "Episode";')
    op.execute('DELETE FROM "Season";')
    op.execute('DELETE FROM "Show";')
    op.execute('DELETE FROM "Movie";')
    op.execute('DELETE FROM "MediaItem";')

    # 4) Drop legacy MediaItem columns no longer used
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {col['name'] for col in inspector.get_columns('MediaItem')}
    legacy_cols = [
        'symlinked', 'symlinked_at', 'symlinked_times', 'symlink_path',
        'file', 'folder', 'alternative_folder', 'update_folder', 'key'
    ]
    with op.batch_alter_table("MediaItem") as batch_op:
        for col in legacy_cols:
            if col in existing_cols:
                try:
                    batch_op.drop_column(col)
                except Exception:
                    # Some backends may not support conditional drops or may have dependencies
                    pass



def downgrade() -> None:
    # Remove FK and column from MediaItem, then drop FilesystemEntry
    with op.batch_alter_table("MediaItem") as batch_op:
        try:
            batch_op.drop_constraint("fk_mediaitem_filesystem_entry_id", type_="foreignkey")
        except Exception:
            pass
        batch_op.drop_column("filesystem_entry_id")

    op.drop_index("ix_filesystem_entry_created_at", table_name="FilesystemEntry")
    op.drop_index("ix_filesystem_entry_provider", table_name="FilesystemEntry")
    op.drop_index("ix_filesystem_entry_path", table_name="FilesystemEntry")
    try:
        op.drop_constraint("uq_filesystem_entry_path", "FilesystemEntry", type_="unique")
    except Exception:
        pass
    op.drop_table("FilesystemEntry")

