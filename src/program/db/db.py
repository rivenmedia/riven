from loguru import logger
from sqla_wrapper import SQLAlchemy
from sqlalchemy import text

from alembic import command
from alembic.config import Config
from program.settings.manager import settings_manager
from program.utils import root_dir

engine_options = {
    "pool_size": 25, # Prom: Set to 1 when debugging sql queries
    "max_overflow": 25, # Prom: Set to 0 when debugging sql queries
    "pool_pre_ping": True, # Prom: Set to False when debugging sql queries
    "pool_recycle": 1800, # Prom: Set to -1 when debugging sql queries
    "echo": False, # Prom: Set to true when debugging sql queries
}

# Prom: This is a good place to set the statement timeout for the database when debugging.
# @event.listens_for(Engine, "connect")
# def set_statement_timeout(dbapi_connection, connection_record):
#     cursor = dbapi_connection.cursor()
#     cursor.execute("SET statement_timeout = 300000")
#     cursor.close()

db_host = settings_manager.settings.database.host
db = SQLAlchemy(db_host, engine_options=engine_options)

def get_db():
    _db = db.Session()
    try:
        yield _db
    finally:
        _db.close()

def create_database_if_not_exists():
    """Create the database if it doesn't exist."""
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
    # PROM: Use the raw connection to execute VACUUM outside a transaction
    try:
        with db.engine.connect() as connection:
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            connection.execute(text("VACUUM;"))
            connection.execute(text("ANALYZE;"))
        logger.log("DATABASE","VACUUM and ANALYZE completed successfully.")
    except Exception as e:
        logger.error(f"Error during VACUUM and ANALYZE: {e}")

def run_migrations():
    """Run any pending migrations on startup"""
    try:
        alembic_cfg = Config(root_dir / "src" / "alembic.ini")
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise