import os
from datetime import datetime

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from loguru import logger
from sqla_wrapper import Alembic, SQLAlchemy
from sqlalchemy import text

from program.settings.manager import settings_manager
from program.utils import data_dir_path

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

script_location = data_dir_path / "alembic/"

if not os.path.exists(script_location):
    os.makedirs(script_location)

alembic = Alembic(db, script_location)
alembic.init(script_location)


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

# https://stackoverflow.com/questions/61374525/how-do-i-check-if-alembic-migrations-need-to-be-generated
def need_upgrade_check() -> bool:
    """Check if there are any pending migrations."""
    with db.engine.connect() as connection:
        mc = MigrationContext.configure(connection)
        diff = compare_metadata(mc, db.Model.metadata)
    return bool(diff)

def ensure_alembic_version_table():
    """Create alembic_version table if it doesn't exist."""
    with db.engine.connect() as connection:
        result = connection.execute(text("SELECT table_name FROM information_schema.tables WHERE table_name = 'alembic_version'"))
        if not result.fetchone():
            logger.log("DATABASE","alembic_version table not found. Creating it...")
            alembic.stamp("head")
            logger.log("DATABASE","alembic_version table created and stamped to head.")

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

def run_migrations(try_again=True) -> None:
    try:
        ensure_alembic_version_table()
        if need_upgrade_check():
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            alembic.revision(f"auto-upg {timestamp}")
            alembic.upgrade()
    except Exception as e:
        logger.warning(f"Error running migrations: {e}")
        db.s.execute(text("delete from alembic_version"))
        db.s.commit()
        alembic.stamp("head")
        if try_again:
            run_migrations(False)
        else:
            exit(1)