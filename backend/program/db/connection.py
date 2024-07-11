# db_connection.py

from sqla_wrapper import SQLAlchemy
from .functions import DbFunctions
from program.settings.manager import settings_manager
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from alembic import command
from alembic.config import Config
from utils.logger import logger
import contextlib
import traceback
import os


class DbConnection(DbFunctions):
    def __init__(self, _logger: logger):
        super().__init__(_logger)
        self.logger = _logger
        self.db = SQLAlchemy(settings_manager.settings.database.host)
        self.script_location = os.path.join(os.getcwd(), "alembic")

        if not os.path.exists(self.script_location):
            os.makedirs(self.script_location)

        self.alembic_cfg = self._create_alembic_config()

    def _create_alembic_config(self) -> Config:
        alembic_cfg = Config()
        alembic_cfg.set_main_option('script_location', self.script_location)
        alembic_cfg.set_main_option('sqlalchemy.url', settings_manager.settings.database.host)
        return alembic_cfg

    @contextlib.contextmanager
    def connect_session(self) -> Session:
        session = None
        try:
            session = Session(bind=self.db.engine)
            yield session
            self.logger.debug("Connected successfully to the database.")
        except SQLAlchemyError as error_:
            self.logger.error(f"Error connecting to the database: {error_} \n {traceback.format_exc()}")
        except Exception as error_:
            self.logger.error(f"Unexpected error: {error_} \n {traceback.format_exc()}")
        finally:
            if session:
                session.close()
                self.logger.debug("Session closed.")

    def close_database_connection(self) -> None:
        if self.db.engine:
            self.db.engine.dispose()
            self.logger.debug("Connection to the database closed.")
        else:
            self.logger.warning("No active connection to the database.")

    def run_migrations(self) -> None:
        try:
            self.logger.info("Running migrations...")
            command.upgrade(self.alembic_cfg, "head")
        except Exception as e:
            self.logger.error(f"Error during migration: {e} \n {traceback.format_exc()}")

    def create_initial_migration(self):
        try:
            self.logger.info("Creating initial migration...")
            command.revision(self.alembic_cfg, message="initial", autogenerate=True)
        except Exception as e:
            self.logger.error(f"Error creating initial migration: {e} \n {traceback.format_exc()}")

    def run(self):
        try:
            if not os.listdir(os.path.join(self.script_location, "versions")):
                self.create_initial_migration()
            self.run_migrations()
        except Exception as e:
            self.logger.error(f"Error during migration: {e} \n {traceback.format_exc()}")