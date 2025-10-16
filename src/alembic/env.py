import logging

from loguru import logger
from sqlalchemy import engine_from_config, pool, text
from sqlalchemy.exc import OperationalError, ProgrammingError

from alembic import context
from program.db.db import db
from program.settings.manager import settings_manager


# Loguru handler for alembic logs
class LoguruHandler(logging.Handler):
    def emit(self, record):
        logger.opt(depth=1, exception=record.exc_info).log(
            "DATABASE", record.getMessage()
        )


# TODO: Will come back to this later...
# if settings_manager.settings.debug_database:
#     # Configure only alembic and SQLAlchemy loggers
#     logging.getLogger("alembic").handlers = [LoguruHandler()]
#     logging.getLogger("alembic").propagate = False
#     logging.getLogger("sqlalchemy").handlers = [LoguruHandler()]
#     logging.getLogger("sqlalchemy").propagate = False

#     # Set log levels
#     logging.getLogger("alembic").setLevel(logging.DEBUG if settings_manager.settings.debug else logging.FATAL)
#     logging.getLogger("sqlalchemy").setLevel(logging.DEBUG if settings_manager.settings.debug else logging.FATAL)

# Alembic configuration
config = context.config
config.set_main_option("sqlalchemy.url", str(settings_manager.settings.database.host))

# Set MetaData object for autogenerate support
target_metadata = db.Model.metadata


def reset_database(connection) -> bool:
    """Reset database if needed"""
    try:
        # Drop and recreate schema
        if db.engine.name == "postgresql":
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
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            connection.execute(text("GRANT ALL ON SCHEMA public TO public"))

        logger.log("DATABASE", "Database reset complete")
        return True
    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        return False


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")

        # Check if user is on a deleted migration revision
        # These revisions were consolidated into the destructive migration
        deleted_revisions = [
            "20250105_1200",  # add_resolution_to_stream
            "9b3030cd23b4",  # add_cascade_ondelete
            "e1f9a0c2b3d4",  # add_filesystementry_and_fk
            "8d9cc5e5f011",  # add_release_metadata_to_items
            "67a4fdbd128b",  # filesystem_relationship_refactor
            "a1b2c3d4e5f6",  # filesystem_and_subtitle_refactor
            "f7ea12c9d1ab",  # reseed_filesystementry_sequence
            "a1b2c3d4e5f7",  # combined_library_profiles
            "b2c3d4e5f8g9",  # add_tvdb_status_to_show
            "c3d4e5f6g7h8",  # remove_path_use_original_filename
            "d4e5f6g7h8i9",  # add_parsed_data_to_media_entry
            "d5e6f7g8h9i0",  # drop_media_entry_unique_constraint
        ]

        try:
            # Check current database version
            result = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).fetchone()
            if result:
                current_version = result[0]

                # Check if current version is in the deleted revisions list
                if any(
                    deleted_rev in current_version for deleted_rev in deleted_revisions
                ):
                    logger.warning("⚠️  MIGRATION CONSOLIDATION DETECTED")
                    logger.warning(
                        f"   Your database is at revision: {current_version}"
                    )
                    logger.warning(
                        "   This revision was consolidated into the destructive migration."
                    )
                    logger.warning(
                        "   Creating snapshot and resetting to base revision 834cba7d26b4..."
                    )

                    # Create a snapshot before resetting
                    from program.utils.cli import snapshot_database
                    from pathlib import Path

                    snapshot_dir = Path("./data/db_snapshot")
                    snapshot_name = f"pre_consolidation_{current_version}"

                    if snapshot_database(snapshot_dir, snapshot_name):
                        logger.log(
                            "DATABASE",
                            f"✅ Snapshot created: {snapshot_dir / (snapshot_name + '.sql')}",
                        )
                    else:
                        logger.warning(
                            "⚠️  Failed to create snapshot, but continuing..."
                        )

                    # Reset to base revision
                    connection.execute(text("DELETE FROM alembic_version"))
                    connection.execute(
                        text(
                            "INSERT INTO alembic_version (version_num) VALUES ('834cba7d26b4')"
                        )
                    )
                    logger.log("DATABASE", f"✅ Reset database version to 834cba7d26b4")
                    logger.log("DATABASE", "   Continuing with migration to head...")
                    # Don't return - continue with normal migration flow
        except Exception as e:
            # If we can't check the version, just continue with normal migration
            logger.debug(f"Could not check alembic version: {e}")

        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,  # Compare column types
                compare_server_default=True,  # Compare default values
                include_schemas=True,  # Include schema in migrations
                render_as_batch=True,  # Enable batch operations
            )

            with context.begin_transaction():
                logger.debug("Starting migrations...")
                context.run_migrations()
                logger.debug("Migrations completed successfully")

        except (OperationalError, ProgrammingError) as e:
            logger.error(f"Database error during migration: {e}")
            logger.warning("Attempting database reset...")

            if reset_database(connection):
                # Configure alembic again after reset
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    compare_type=True,
                    compare_server_default=True,
                    include_schemas=True,
                    render_as_batch=True,
                )

                # Try migrations again
                with context.begin_transaction():
                    logger.debug("Rerunning migrations after reset...")
                    context.run_migrations()
                    logger.debug("Migrations completed successfully")
            else:
                raise Exception("Migration recovery failed")

        except Exception as e:
            logger.error(f"Unexpected error during migration: {e}")
            raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
