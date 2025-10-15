"""add_filesystementry_and_fk

Revision ID: e1f9a0c2b3d4
Revises: 8d9cc5e5f011
Create Date: 2025-09-11 12:10:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f9a0c2b3d4"
down_revision: Union[str, None] = "8d9cc5e5f011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Prepare DB inspection utilities
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1) Create FilesystemEntry table (idempotent + with safety checks)
    if "FilesystemEntry" not in existing_tables:
        op.create_table(
            "FilesystemEntry",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("path", sa.String(), nullable=False),
            sa.Column(
                "file_size",
                sa.BigInteger(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "is_directory",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("original_filename", sa.String(), nullable=True),
            sa.Column("original_folder", sa.String(), nullable=True),
            sa.Column("download_url", sa.String(), nullable=True),
            sa.Column("unrestricted_url", sa.String(), nullable=True),
            sa.Column("provider", sa.String(), nullable=True),
            sa.Column("provider_download_id", sa.String(), nullable=True),
            sa.Column(
                "available_in_vfs",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.CheckConstraint(
                "file_size >= 0", name="ck_filesystem_entry_file_size_nonneg"
            ),
            sa.CheckConstraint("path <> ''", name="ck_filesystem_entry_path_nonempty"),
        )
        # refresh inspector cache
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())

    # Ensure unique constraint and indexes exist (idempotent)
    if "FilesystemEntry" in existing_tables:
        existing_ucs = {
            uc.get("name") for uc in inspector.get_unique_constraints("FilesystemEntry")
        }
        existing_ixs = {
            ix.get("name") for ix in inspector.get_indexes("FilesystemEntry")
        }

        if "uq_filesystem_entry_path" not in existing_ucs:
            try:
                op.create_unique_constraint(
                    "uq_filesystem_entry_path", "FilesystemEntry", ["path"]
                )
            except Exception:
                pass

        if "ix_filesystem_entry_path" not in existing_ixs:
            try:
                op.create_index(
                    "ix_filesystem_entry_path",
                    "FilesystemEntry",
                    ["path"],
                    unique=False,
                )
            except Exception:
                pass

        if "ix_filesystem_entry_provider" not in existing_ixs:
            try:
                op.create_index(
                    "ix_filesystem_entry_provider",
                    "FilesystemEntry",
                    ["provider"],
                    unique=False,
                )
            except Exception:
                pass

        if "ix_filesystem_entry_created_at" not in existing_ixs:
            try:
                op.create_index(
                    "ix_filesystem_entry_created_at",
                    "FilesystemEntry",
                    ["created_at"],
                    unique=False,
                )
            except Exception:
                pass

    # 2) Add MediaItem.filesystem_entry_id (nullable FK) and updated flag safely
    mediaitem_cols = {col["name"] for col in inspector.get_columns("MediaItem")}
    if "filesystem_entry_id" not in mediaitem_cols:
        op.add_column(
            "MediaItem",
            sa.Column("filesystem_entry_id", sa.Integer(), nullable=True),
        )

    if "updated" not in mediaitem_cols:
        # Add with server_default to satisfy existing rows, then drop default
        op.add_column(
            "MediaItem",
            sa.Column(
                "updated", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
        )
        op.alter_column(
            "MediaItem",
            "updated",
            server_default=None,
            existing_type=sa.Boolean(),
            existing_nullable=False,
        )

    # Create FK if missing
    mediaitem_fks = {fk.get("name") for fk in inspector.get_foreign_keys("MediaItem")}
    if (
        "fk_mediaitem_filesystem_entry_id" not in mediaitem_fks
        and "filesystem_entry_id"
        in {col["name"] for col in inspector.get_columns("MediaItem")}
    ):
        op.create_foreign_key(
            "fk_mediaitem_filesystem_entry_id",
            "MediaItem",
            "FilesystemEntry",
            ["filesystem_entry_id"],
            ["id"],
            ondelete=None,
        )

    # 3) Destructive data migration: purge all MediaItems to reset state (guarded by table existence)
    # Note: This will remove all user media items and related subtype rows.
    tables_to_clear = [
        "Subtitle",
        "StreamRelation",
        "StreamBlacklistRelation",
        "Episode",
        "Season",
        "Show",
        "Movie",
        "MediaItem",
    ]
    existing_tables = set(sa.inspect(bind).get_table_names())
    for table_name in tables_to_clear:
        if table_name in existing_tables:
            op.execute(sa.text(f'DELETE FROM "{table_name}";'))

    # 4) Drop legacy MediaItem columns no longer used
    existing_cols = {col["name"] for col in sa.inspect(bind).get_columns("MediaItem")}
    legacy_cols = [
        "symlinked",
        "symlinked_at",
        "symlinked_times",
        "symlink_path",
        "file",
        "folder",
        "alternative_folder",
        "update_folder",
        "key",
    ]
    with op.batch_alter_table("MediaItem") as batch_op:
        for col in legacy_cols:
            if col in existing_cols:
                batch_op.drop_column(col)


def downgrade() -> None:
    # Remove FK and columns from MediaItem, then drop FilesystemEntry (with existence checks)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    mediaitem_cols = {col["name"] for col in inspector.get_columns("MediaItem")}
    mediaitem_fks = {fk.get("name") for fk in inspector.get_foreign_keys("MediaItem")}

    with op.batch_alter_table("MediaItem") as batch_op:
        if "fk_mediaitem_filesystem_entry_id" in mediaitem_fks:
            batch_op.drop_constraint(
                "fk_mediaitem_filesystem_entry_id", type_="foreignkey"
            )
        if "filesystem_entry_id" in mediaitem_cols:
            batch_op.drop_column("filesystem_entry_id")
        if "updated" in mediaitem_cols:
            batch_op.drop_column("updated")

    existing_tables = set(inspector.get_table_names())
    if "FilesystemEntry" in existing_tables:
        existing_ixs = {
            ix.get("name") for ix in inspector.get_indexes("FilesystemEntry")
        }
        if "ix_filesystem_entry_created_at" in existing_ixs:
            op.drop_index(
                "ix_filesystem_entry_created_at", table_name="FilesystemEntry"
            )
        if "ix_filesystem_entry_provider" in existing_ixs:
            op.drop_index("ix_filesystem_entry_provider", table_name="FilesystemEntry")
        if "ix_filesystem_entry_path" in existing_ixs:
            op.drop_index("ix_filesystem_entry_path", table_name="FilesystemEntry")
        existing_ucs = {
            uc.get("name") for uc in inspector.get_unique_constraints("FilesystemEntry")
        }
        if "uq_filesystem_entry_path" in existing_ucs:
            op.drop_constraint(
                "uq_filesystem_entry_path", "FilesystemEntry", type_="unique"
            )
        op.drop_table("FilesystemEntry")
