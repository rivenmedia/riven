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
    1. Drop all existing tables and data
    2. Create the new schema with FilesystemEntry architecture

    Note: No automatic snapshot/backup is performed by this migration.
    """
    # Get the connection from the current context
    connection = op.get_bind()

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
    Downgrade is not supported for this destructive migration.

    This migration resets the database schema.
    """
    logger.error("Downgrade is not supported for this destructive migration.")
    raise Exception("Downgrade is not supported for this destructive migration.")
