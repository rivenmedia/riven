"""destructive_migration_filesystem_and_profiles

This is a DESTRUCTIVE migration that resets the database and rebuilds the schema.
All existing data will be lost.

Major changes:
- Removed legacy symlink fields (symlinked, symlinked_at, symlinked_times, symlink_path, file, folder, alternative_folder)
- Introduced FilesystemEntry polymorphic base class
- Added MediaEntry (for video files) and SubtitleEntry (for subtitles) as FilesystemEntry children
- Added library_profiles field to MediaEntry for multi-library support
- Added parsed_data field to MediaEntry for caching PTT parse results
- Added metadata fields to MediaItem (rating, content_rating, network, country, language, aired_at)
- Added tvdb_status field to Show
- Removed unique constraint on MediaEntry.original_filename to allow multi-profile downloads

Revision ID: 7e5b5cf430ff
Revises: 834cba7d26b4
Create Date: 2025-10-16 10:00:31.510728

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from loguru import logger


# revision identifiers, used by Alembic.
revision: str = "7e5b5cf430ff"
down_revision: Union[str, None] = "834cba7d26b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def reset_database(connection) -> bool:
    """Reset database by dropping and recreating the public schema"""
    try:
        # Terminate all other connections to the database
        if connection.engine.name == "postgresql":
            connection.execute(
                text(
                    """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                AND pid <> pg_backend_pid()
            """
                )
            )
            # Drop and recreate schema
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            connection.execute(text("GRANT ALL ON SCHEMA public TO public"))

        logger.log("DATABASE", "Database reset complete")
        return True
    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        return False


def upgrade() -> None:
    """
    Destructive upgrade: Reset database and create new schema from scratch.

    This migration will:
    1. Create a named database snapshot (pre_834cba7d26b4) before making changes
    2. Drop all existing tables and data
    3. Create the new schema with FilesystemEntry architecture

    Note: This migration does NOT recreate alembic_version - Alembic handles that automatically.
    """
    # Get the connection from the current context
    connection = op.get_bind()

    # Create a named snapshot before destructive changes
    # This snapshot can be used to restore the database if needed
    logger.warning(
        "⚠️  DESTRUCTIVE MIGRATION: Creating database snapshot before migration..."
    )
    from program.utils.cli import snapshot_database
    from pathlib import Path

    snapshot_dir = Path("./data/db_snapshot")
    snapshot_name = "pre_destructive_migration_834cba7d26b4"

    if snapshot_database(snapshot_dir, snapshot_name):
        logger.log(
            "DATABASE",
            f"✅ Database snapshot created: {snapshot_dir / (snapshot_name + '.sql')}",
        )
        logger.log("DATABASE", f"   To restore: alembic downgrade -1")
    else:
        logger.error("❌ Failed to create database snapshot!")
        logger.warning(
            "⚠️  Migration will continue, but you may want to create a manual backup."
        )
        # Don't fail the migration if snapshot fails - user might not have pg_dump available

    # Reset the database
    logger.warning(
        "⚠️  DESTRUCTIVE MIGRATION: Resetting database and dropping all data..."
    )
    if not reset_database(connection):
        raise Exception("Failed to reset database")

    # Now create all tables from scratch using the current models
    # The metadata will be imported from the models
    from program.db.db import db

    # Create all application tables
    db.Model.metadata.create_all(bind=connection)

    # Manually create alembic_version table since we dropped it
    # Alembic needs this table to exist before it can update the version
    connection.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS alembic_version (
            version_num VARCHAR(32) NOT NULL,
            CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
        )
        """
        )
    )

    # Insert the old version so Alembic can update it to the new version
    # This is what Alembic expects: it will UPDATE this to '7e5b5cf430ff' after upgrade() completes
    connection.execute(
        text("INSERT INTO alembic_version (version_num) VALUES ('834cba7d26b4')")
    )

    logger.log("DATABASE", "✅ Database schema recreated successfully")
    logger.log(
        "DATABASE", "   All data has been cleared - you can now add new media items"
    )


def downgrade() -> None:
    """
    Downgrade by restoring from the pre-migration snapshot.

    This will:
    1. Check if the pre-migration snapshot exists
    2. Restore the database from the snapshot (which includes alembic_version)
    3. The snapshot already contains the correct alembic_version (834cba7d26b4)

    Note: After restore, Alembic may show an error about version mismatch, but this is
    expected because the restore operation sets the version directly. The database will
    be in the correct state.
    """
    from program.utils.cli import restore_database
    from pathlib import Path

    snapshot_dir = Path("./data/db_snapshot")
    snapshot_name = "pre_destructive_migration_834cba7d26b4.sql"
    snapshot_file = snapshot_dir / snapshot_name

    if not snapshot_file.exists():
        logger.error(f"❌ Snapshot file not found: {snapshot_file}")
        logger.error("Cannot downgrade without the pre-migration snapshot.")
        logger.error(
            "The snapshot should have been created automatically during upgrade."
        )
        raise Exception(
            f"Downgrade failed: Snapshot file not found at {snapshot_file}. "
            "Please restore from a manual backup if available."
        )

    logger.warning("⚠️  DOWNGRADE: Restoring database from pre-migration snapshot...")
    logger.log("DATABASE", f"Restoring from: {snapshot_file}")

    # Get connection to manually update alembic_version after restore
    connection = op.get_bind()

    if restore_database(snapshot_file):
        logger.log("DATABASE", "✅ Database restored successfully from snapshot")

        # The restore includes alembic_version table set to 834cba7d26b4
        # But Alembic expects to find 7e5b5cf430ff so it can update it to 834cba7d26b4
        # We need to temporarily set it to the current version so Alembic can update it
        try:
            connection.execute(text("DELETE FROM alembic_version"))
            connection.execute(
                text(
                    "INSERT INTO alembic_version (version_num) VALUES ('7e5b5cf430ff')"
                )
            )
            logger.log("DATABASE", "   Prepared alembic_version for downgrade tracking")
        except Exception as e:
            # If this fails, the restore still worked, just log it
            logger.warning(f"Could not update alembic_version: {e}")
            logger.log(
                "DATABASE",
                "   Database is restored, but alembic version tracking may be inconsistent",
            )
    else:
        logger.error("❌ Failed to restore database from snapshot!")
        raise Exception("Downgrade failed: Could not restore database from snapshot")
