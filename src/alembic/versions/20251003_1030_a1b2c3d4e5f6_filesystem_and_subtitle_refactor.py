"""Filesystem and subtitle refactor with polymorphic inheritance

Revision ID: a1b2c3d4e5f6
Revises: 67a4fdbd128b
Create Date: 2025-10-03 10:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "67a4fdbd128b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Combined migration that:
    1. Refactors FilesystemEntry and Subtitle to use polymorphic inheritance
    2. Moves file_size and is_directory to base FilesystemEntry
    3. Adds parsed_data JSON column to MediaItem

    Creates a new base FilesystemEntry table with common fields, then creates
    MediaEntry and SubtitleEntry as joined-table inheritance subclasses.

    WARNING: This migration will DELETE all existing Subtitle entries as they
    need to be recreated with the new schema and OpenSubtitles integration.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # =========================================================================
    # Step 1: Drop existing Subtitle table and all its data
    # =========================================================================
    if "Subtitle" in existing_tables:
        # Drop indexes first
        subtitle_indexes = [idx["name"] for idx in inspector.get_indexes("Subtitle")]
        for idx_name in subtitle_indexes:
            try:
                op.drop_index(idx_name, table_name="Subtitle")
            except Exception:
                pass

        # Drop constraints
        subtitle_constraints = [
            c["name"] for c in inspector.get_unique_constraints("Subtitle")
        ]
        for constraint_name in subtitle_constraints:
            try:
                op.drop_constraint(constraint_name, "Subtitle", type_="unique")
            except Exception:
                pass

        # Drop foreign keys
        subtitle_fks = [fk["name"] for fk in inspector.get_foreign_keys("Subtitle")]
        for fk_name in subtitle_fks:
            try:
                op.drop_constraint(fk_name, "Subtitle", type_="foreignkey")
            except Exception:
                pass

        # Drop the table
        op.drop_table("Subtitle")

    # =========================================================================
    # Step 2: Rename existing FilesystemEntry to FilesystemEntry_old
    # =========================================================================
    if "FilesystemEntry" in existing_tables:
        op.rename_table("FilesystemEntry", "FilesystemEntry_old")
        # Refresh inspector
        inspector = sa.inspect(bind)
        existing_tables = set(inspector.get_table_names())

    # =========================================================================
    # Step 3: Create new base FilesystemEntry table with common fields
    # Including file_size and is_directory from the start
    # =========================================================================
    op.create_table(
        "FilesystemEntry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entry_type", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column(
            "file_size", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_directory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "available_in_vfs",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("media_item_id", sa.Integer(), nullable=True),
    )

    # Refresh inspector after table creation
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Create unique constraint and indexes on base table (idempotent)
    existing_constraints = {
        c["name"] for c in inspector.get_unique_constraints("FilesystemEntry")
    }
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("FilesystemEntry")}
    existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("FilesystemEntry")}

    if "uq_filesystem_entry_path" not in existing_constraints:
        try:
            op.create_unique_constraint(
                "uq_filesystem_entry_path", "FilesystemEntry", ["path"]
            )
        except Exception:
            pass

    if "ix_filesystem_entry_path" not in existing_indexes:
        try:
            op.create_index("ix_filesystem_entry_path", "FilesystemEntry", ["path"])
        except Exception:
            pass

    if "ix_filesystem_entry_entry_type" not in existing_indexes:
        try:
            op.create_index(
                "ix_filesystem_entry_entry_type", "FilesystemEntry", ["entry_type"]
            )
        except Exception:
            pass

    if "ix_filesystem_entry_media_item_id" not in existing_indexes:
        try:
            op.create_index(
                "ix_filesystem_entry_media_item_id",
                "FilesystemEntry",
                ["media_item_id"],
            )
        except Exception:
            pass

    if "ix_filesystem_entry_created_at" not in existing_indexes:
        try:
            op.create_index(
                "ix_filesystem_entry_created_at", "FilesystemEntry", ["created_at"]
            )
        except Exception:
            pass

    # Create foreign key to MediaItem
    if "fk_filesystementry_media_item_id" not in existing_fks:
        try:
            op.create_foreign_key(
                "fk_filesystementry_media_item_id",
                "FilesystemEntry",
                "MediaItem",
                ["media_item_id"],
                ["id"],
                ondelete="CASCADE",
            )
        except Exception:
            pass

    # =========================================================================
    # Step 4: Create MediaEntry table (joined table inheritance)
    # Without file_size and is_directory (they're in base now)
    # =========================================================================
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "MediaEntry" not in existing_tables:
        op.create_table(
            "MediaEntry",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("original_filename", sa.String(), nullable=True),
            sa.Column("download_url", sa.String(), nullable=True),
            sa.Column("unrestricted_url", sa.String(), nullable=True),
            sa.Column("provider", sa.String(), nullable=True),
            sa.Column("provider_download_id", sa.String(), nullable=True),
        )

    # Refresh inspector
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "MediaEntry" in existing_tables:
        existing_fks = {fk["name"] for fk in inspector.get_foreign_keys("MediaEntry")}
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("MediaEntry")}

        # Create foreign key to base FilesystemEntry
        if "fk_mediaentry_id" not in existing_fks:
            try:
                op.create_foreign_key(
                    "fk_mediaentry_id",
                    "MediaEntry",
                    "FilesystemEntry",
                    ["id"],
                    ["id"],
                    ondelete="CASCADE",
                )
            except Exception:
                pass

        # Create indexes on MediaEntry
        if "ix_media_entry_provider" not in existing_indexes:
            try:
                op.create_index("ix_media_entry_provider", "MediaEntry", ["provider"])
            except Exception:
                pass

    # =========================================================================
    # Step 5: Migrate data from FilesystemEntry_old to new tables
    # =========================================================================
    if "FilesystemEntry_old" in existing_tables:
        # Insert into base FilesystemEntry table (with file_size and is_directory)
        op.execute(
            """
            INSERT INTO "FilesystemEntry" (id, entry_type, path, file_size, is_directory, created_at, updated_at, available_in_vfs, media_item_id)
            SELECT 
                id,
                'media' as entry_type,
                path,
                COALESCE(file_size, 0) as file_size,
                COALESCE(is_directory, false) as is_directory,
                COALESCE(created_at, CURRENT_TIMESTAMP) as created_at,
                COALESCE(updated_at, CURRENT_TIMESTAMP) as updated_at,
                COALESCE(available_in_vfs, false) as available_in_vfs,
                media_item_id
            FROM "FilesystemEntry_old"
        """
        )

        # Insert into MediaEntry table (without file_size and is_directory)
        op.execute(
            """
            INSERT INTO "MediaEntry" (id, original_filename, download_url, unrestricted_url, provider, provider_download_id)
            SELECT 
                id,
                original_filename,
                download_url,
                unrestricted_url,
                provider,
                provider_download_id
            FROM "FilesystemEntry_old"
        """
        )

    # =========================================================================
    # Step 6: Create SubtitleEntry table (joined table inheritance)
    # =========================================================================
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "SubtitleEntry" not in existing_tables:
        op.create_table(
            "SubtitleEntry",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("language", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("file_hash", sa.String(), nullable=True),
            sa.Column("video_file_size", sa.BigInteger(), nullable=True),
            sa.Column("opensubtitles_id", sa.String(), nullable=True),
        )

    # Refresh inspector
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "SubtitleEntry" in existing_tables:
        existing_fks = {
            fk["name"] for fk in inspector.get_foreign_keys("SubtitleEntry")
        }
        existing_indexes = {
            idx["name"] for idx in inspector.get_indexes("SubtitleEntry")
        }

        # Create foreign key to base FilesystemEntry
        if "fk_subtitleentry_id" not in existing_fks:
            try:
                op.create_foreign_key(
                    "fk_subtitleentry_id",
                    "SubtitleEntry",
                    "FilesystemEntry",
                    ["id"],
                    ["id"],
                    ondelete="CASCADE",
                )
            except Exception:
                pass

        # Create indexes on SubtitleEntry
        if "ix_subtitle_entry_language" not in existing_indexes:
            try:
                op.create_index(
                    "ix_subtitle_entry_language", "SubtitleEntry", ["language"]
                )
            except Exception:
                pass

        if "ix_subtitle_entry_file_hash" not in existing_indexes:
            try:
                op.create_index(
                    "ix_subtitle_entry_file_hash", "SubtitleEntry", ["file_hash"]
                )
            except Exception:
                pass

        if "ix_subtitle_entry_opensubtitles_id" not in existing_indexes:
            try:
                op.create_index(
                    "ix_subtitle_entry_opensubtitles_id",
                    "SubtitleEntry",
                    ["opensubtitles_id"],
                )
            except Exception:
                pass

    # =========================================================================
    # Step 7: Drop old FilesystemEntry_old table
    # =========================================================================
    if "FilesystemEntry_old" in existing_tables:
        # Drop indexes
        old_indexes = [
            idx["name"] for idx in inspector.get_indexes("FilesystemEntry_old")
        ]
        for idx_name in old_indexes:
            try:
                op.drop_index(idx_name, table_name="FilesystemEntry_old")
            except Exception:
                pass

        # Drop constraints
        old_constraints = [
            c["name"] for c in inspector.get_unique_constraints("FilesystemEntry_old")
        ]
        for constraint_name in old_constraints:
            try:
                op.drop_constraint(
                    constraint_name, "FilesystemEntry_old", type_="unique"
                )
            except Exception:
                pass

        # Drop foreign keys
        old_fks = [
            fk["name"] for fk in inspector.get_foreign_keys("FilesystemEntry_old")
        ]
        for fk_name in old_fks:
            try:
                op.drop_constraint(fk_name, "FilesystemEntry_old", type_="foreignkey")
            except Exception:
                pass

        # Drop the table
        op.drop_table("FilesystemEntry_old")

    # =========================================================================
    # Step 8: Add parsed_data JSON column to MediaItem
    # =========================================================================
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("MediaItem")}

    if "parsed_data" not in columns:
        op.add_column("MediaItem", sa.Column("parsed_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    """
    Revert all changes:
    1. Remove parsed_data from MediaItem
    2. Revert polymorphic inheritance back to separate FilesystemEntry and Subtitle tables
    3. Move file_size and is_directory back to FilesystemEntry (not base)

    WARNING: This will lose SubtitleEntry data as the old Subtitle schema is incompatible.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # =========================================================================
    # Step 1: Remove parsed_data from MediaItem
    # =========================================================================
    columns = {col["name"] for col in inspector.get_columns("MediaItem")}

    if "parsed_data" in columns:
        with op.batch_alter_table("MediaItem") as batch_op:
            batch_op.drop_column("parsed_data")

    # =========================================================================
    # Step 2: Create temporary table to hold MediaEntry data
    # =========================================================================
    op.create_table(
        "FilesystemEntry_new",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column(
            "file_size", sa.BigInteger(), nullable=False, server_default=sa.text("0")
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
        sa.Column("media_item_id", sa.Integer(), nullable=True),
    )

    # =========================================================================
    # Step 3: Migrate MediaEntry data back to old schema
    # =========================================================================
    if "MediaEntry" in existing_tables and "FilesystemEntry" in existing_tables:
        op.execute(
            """
            INSERT INTO "FilesystemEntry_new"
            (id, path, file_size, is_directory, created_at, updated_at, original_filename,
             download_url, unrestricted_url, provider, provider_download_id, available_in_vfs, media_item_id)
            SELECT
                fe.id, fe.path, fe.file_size, fe.is_directory, fe.created_at, fe.updated_at,
                me.original_filename, me.download_url, me.unrestricted_url, me.provider,
                me.provider_download_id, fe.available_in_vfs, fe.media_item_id
            FROM "FilesystemEntry" fe
            JOIN "MediaEntry" me ON fe.id = me.id
            WHERE fe.entry_type = 'media'
        """
        )

    # =========================================================================
    # Step 4: Drop new tables
    # =========================================================================
    tables_to_drop = ["SubtitleEntry", "MediaEntry", "FilesystemEntry"]
    for table_name in tables_to_drop:
        if table_name in existing_tables:
            # Drop indexes
            indexes = [idx["name"] for idx in inspector.get_indexes(table_name)]
            for idx_name in indexes:
                try:
                    op.drop_index(idx_name, table_name=table_name)
                except Exception:
                    pass

            # Drop constraints
            constraints = [
                c["name"] for c in inspector.get_unique_constraints(table_name)
            ]
            for constraint_name in constraints:
                try:
                    op.drop_constraint(constraint_name, table_name, type_="unique")
                except Exception:
                    pass

            # Drop foreign keys
            fks = [fk["name"] for fk in inspector.get_foreign_keys(table_name)]
            for fk_name in fks:
                try:
                    op.drop_constraint(fk_name, table_name, type_="foreignkey")
                except Exception:
                    pass

            # Drop table
            op.drop_table(table_name)

    # =========================================================================
    # Step 5: Rename FilesystemEntry_new back to FilesystemEntry
    # =========================================================================
    op.rename_table("FilesystemEntry_new", "FilesystemEntry")

    # Recreate indexes and constraints
    op.create_unique_constraint("uq_filesystem_entry_path", "FilesystemEntry", ["path"])
    op.create_index("ix_filesystem_entry_path", "FilesystemEntry", ["path"])
    op.create_index("ix_filesystem_entry_provider", "FilesystemEntry", ["provider"])
    op.create_index("ix_filesystem_entry_created_at", "FilesystemEntry", ["created_at"])
    op.create_index(
        "ix_filesystem_entry_media_item_id", "FilesystemEntry", ["media_item_id"]
    )

    # Recreate foreign key
    op.create_foreign_key(
        "fk_filesystementry_media_item_id",
        "FilesystemEntry",
        "MediaItem",
        ["media_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
