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
        logger.opt(depth=1, exception=record.exc_info).log("DATABASE", record.getMessage())

if settings_manager.settings.debug_database:
    # Configure only alembic and SQLAlchemy loggers
    logging.getLogger("alembic").handlers = [LoguruHandler()]
    logging.getLogger("alembic").propagate = False
    logging.getLogger("sqlalchemy").handlers = [LoguruHandler()]
    logging.getLogger("sqlalchemy").propagate = False

    # Set log levels
    logging.getLogger("alembic").setLevel(logging.DEBUG if settings_manager.settings.debug else logging.FATAL)
    logging.getLogger("sqlalchemy").setLevel(logging.DEBUG if settings_manager.settings.debug else logging.FATAL)

# Alembic configuration
config = context.config
config.set_main_option("sqlalchemy.url", settings_manager.settings.database.host)

# Set MetaData object for autogenerate support
target_metadata = db.Model.metadata

def reset_database(connection) -> bool:
    """Reset database if needed"""
    try:
        # Drop and recreate schema
        if db.engine.name == "postgresql":
            connection.execute(text("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = current_database()
                AND pid <> pg_backend_pid()
            """))
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