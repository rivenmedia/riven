"""Database initialization and management utilities."""
from loguru import logger
from sqla_wrapper import SQLAlchemy
from sqlalchemy import text

from alembic import command
from alembic.config import Config
from program.settings.manager import settings_manager
from program.utils import root_dir

# Database connection pool settings
# For debugging SQL queries, adjust these values:
# - pool_size: 1 (limit connections)
# - max_overflow: 0 (no overflow)
# - pool_pre_ping: False (disable connection health checks)
# - pool_recycle: -1 (disable connection recycling)
# - echo: True (log all SQL statements)
engine_options = {
    "pool_size": 25,
    "max_overflow": 25,
    "pool_pre_ping": True,
    "pool_recycle": 1800,
    "echo": False,
}

# For debugging: Set statement timeout for long-running queries
# @event.listens_for(Engine, "connect")
# def set_statement_timeout(dbapi_connection, connection_record):
#     cursor = dbapi_connection.cursor()
#     cursor.execute("SET statement_timeout = 300000")
#     cursor.close()

db_host = str(settings_manager.settings.database.host)
db = SQLAlchemy(db_host, engine_options=engine_options)

def get_db():
    """
    FastAPI dependency for database sessions.

    Yields a database session and ensures it's closed after use.
    """
    _db = db.Session()
    try:
        yield _db
    finally:
        _db.close()

def create_database_if_not_exists():
    """
    Create the database if it doesn't exist.

    Attempts to create the database by connecting to the base host
    and executing a CREATE DATABASE command.

    Returns:
        bool: True if database was created successfully, False otherwise.
    """
    db_name = db_host.split("/")[-1]
    db_base_host = "/".join(db_host.split("/")[:-1])
    try:
        temp_db = SQLAlchemy(db_base_host, engine_options=engine_options)
        with temp_db.engine.connect() as connection:
            connection.execution_options(isolation_level="AUTOCOMMIT").execute(text(f"CREATE DATABASE {db_name}"))
        return True
    except Exception as e:
        logger.error(f"Failed to create database {db_name}: {e}")
        return False

def vacuum_and_analyze_index_maintenance() -> None:
    """
    Run VACUUM and ANALYZE on the database for maintenance.

    This optimizes the database by reclaiming storage and updating
    query planner statistics. Must be run outside a transaction.
    """
    try:
        with db.engine.connect() as connection:
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            connection.execute(text("VACUUM;"))
            connection.execute(text("ANALYZE;"))
        logger.log("DATABASE", "VACUUM and ANALYZE completed successfully.")
    except Exception as e:
        logger.error(f"Error during VACUUM and ANALYZE: {e}")

def run_migrations(database_url=None):
    """
    Run any pending Alembic migrations on startup.

    Args:
        database_url: Optional database URL to override the default from alembic.ini.

    Raises:
        Exception: If migration fails.
    """
    try:
        alembic_cfg = Config(root_dir / "src" / "alembic.ini")
        if database_url:
            alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

def dev_reset_database():
    """
    [DEV ONLY] Drop all tables and recreate from models without running migrations.

    This is useful for development when you want to test schema changes without
    creating migrations. WARNING: This will delete ALL data in the database!
    """
    logger.warning("=" * 80)
    logger.warning("DEV MODE: Dropping all tables and recreating from models")
    logger.warning("This will DELETE ALL DATA in the database!")
    logger.warning("=" * 80)

    try:
        # Drop and recreate the entire public schema
        # This is the cleanest way to reset everything (tables, enums, sequences, etc.)
        logger.info("Dropping entire public schema...")

        with db.engine.connect() as connection:
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")

            # Drop the entire public schema with CASCADE
            # This removes everything: tables, enums, sequences, functions, etc.
            connection.execute(text('DROP SCHEMA IF EXISTS public CASCADE'))
            logger.debug("Public schema dropped")

            # Recreate the public schema
            connection.execute(text('CREATE SCHEMA public'))
            logger.debug("Public schema recreated")

            # Grant permissions (standard PostgreSQL setup)
            connection.execute(text('GRANT ALL ON SCHEMA public TO PUBLIC'))
            logger.debug("Permissions granted")

        logger.success("Database completely reset (schema dropped and recreated)")

        # Create all tables from models
        logger.info("Creating tables from models...")
        db.Model.metadata.create_all(db.engine)
        logger.success("All tables created from models")

        logger.success("Dev database reset complete!")
        logger.info("Starting application with fresh database...")

    except Exception as e:
        logger.error(f"Dev database reset failed: {e}")
        raise