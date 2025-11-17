from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from loguru import logger
from sqla_wrapper import SQLAlchemy, Session
from sqlalchemy import text, orm

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from program.settings.manager import settings_manager
from program.utils import root_dir

engine_options = {
    "pool_size": 25,  # Prom: Set to 1 when debugging sql queries
    "max_overflow": 25,  # Prom: Set to 0 when debugging sql queries
    "pool_pre_ping": True,  # Prom: Set to False when debugging sql queries
    "pool_recycle": 1800,  # Prom: Set to -1 when debugging sql queries
    "echo": False,  # Prom: Set to true when debugging sql queries
}

# Prom: This is a good place to set the statement timeout for the database when debugging.
# @event.listens_for(Engine, "connect")
# def set_statement_timeout(dbapi_connection, connection_record):
#     cursor = dbapi_connection.cursor()
#     cursor.execute("SET statement_timeout = 300000")
#     cursor.close()

db_host = str(settings_manager.settings.database.host)
db = SQLAlchemy(db_host, engine_options=engine_options)


class BaseModel(orm.DeclarativeBase):
    """Base class for all database models"""

    pass


@contextmanager
def db_session() -> Generator[Session, Any, None]:
    with db.Session() as session:
        s: Session = session

        yield s


def create_database_if_not_exists():
    """Create the database if it doesn't exist."""
    db_name = db_host.split("/")[-1]
    db_base_host = "/".join(db_host.split("/")[:-1])
    try:
        temp_db = SQLAlchemy(db_base_host, engine_options=engine_options)
        with temp_db.engine.connect() as connection:
            connection.execution_options(isolation_level="AUTOCOMMIT").execute(
                text(f"CREATE DATABASE {db_name}")
            )
        return True
    except Exception as e:
        logger.error(f"Failed to create database {db_name}: {e}")
        return False


def vacuum_and_analyze_index_maintenance() -> None:
    try:
        with db.engine.connect() as connection:
            connection = connection.execution_options(isolation_level="AUTOCOMMIT")
            connection.execute(text("VACUUM;"))
            connection.execute(text("ANALYZE;"))
        logger.log("DATABASE", "VACUUM and ANALYZE completed successfully.")
    except Exception as e:
        logger.error(f"Error during VACUUM and ANALYZE: {e}")


def reset_database():
    """Reset the database by dropping and recreating the public schema."""
    logger.warning("Resetting database - all data will be lost!")
    try:
        with db.engine.connect() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
            conn.commit()
        logger.success("Database reset complete")
        return True
    except Exception as e:
        logger.error(f"Failed to reset database: {e}")
        return False


def run_migrations(database_url: str | None = None):
    """Run any pending migrations on startup.

    If a pre-v1 database is detected (revision not in current migration chain),
    automatically reset the database and create the v1 schema from scratch.

    Special case: Latest dev branch (7e5b5cf430ff) has identical schema to v1_base,
    so we can migrate it directly without data loss.
    """
    try:
        alembic_cfg = Config(root_dir / "src" / "alembic.ini")
        if database_url:
            alembic_cfg.set_main_option("sqlalchemy.url", database_url)

        # Get script directory to check migration chain
        script = ScriptDirectory.from_config(alembic_cfg)

        # Check current database revision
        with db.engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        # Get all revisions in the current migration chain (from base to head)
        # This includes v1_base and any future migrations built on top of it
        head_rev = script.get_current_head()
        current_chain = set[str]()

        if head_rev:
            # Walk down from head to base, collecting all revisions
            for rev in script.walk_revisions(base="base", head=head_rev):
                current_chain.add(rev.revision)

        # Special case: Latest dev branch has identical schema to v1_base
        # Migrate it directly without resetting to preserve user data
        latest_dev_revision = "7e5b5cf430ff"
        v1_base_revision = "4f327e05c40f"

        if current_rev == latest_dev_revision:
            logger.info(f"Detected latest dev branch (revision: {current_rev})")
            logger.info("Migrating to v1 without data loss (schema is identical)")

            # Update alembic_version to v1_base directly
            with db.engine.connect() as conn:
                conn.execute(
                    text(
                        f"UPDATE alembic_version SET version_num = '{v1_base_revision}'"
                    )
                )
                conn.commit()

            logger.success("Migrated from dev branch to v1_base")

            # Continue with normal upgrade
            command.upgrade(alembic_cfg, "head")
            logger.success("Database migrations completed successfully")

            return

        # If database has a revision that's NOT in the current chain, it's pre-v1
        # This handles old v0/dev branches while allowing new v1.x migrations
        if current_rev is not None and current_rev not in current_chain:
            logger.warning(f"Detected pre-v1 database (revision: {current_rev})")
            logger.warning(
                "Upgrading to v1 requires database reset (data cannot be migrated)"
            )
            logger.warning(
                "This affects all pre-v1 databases including v0 releases and dev branches"
            )

            if not reset_database():
                raise Exception("Failed to reset database for v1 upgrade")

            logger.info("Creating v1 schema from scratch...")

        # Run migrations to head (v1 schema)
        command.upgrade(alembic_cfg, "head")
        logger.success("Database migrations completed successfully")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
