from sqla_wrapper import Alembic, SQLAlchemy
from program.settings.manager import settings_manager
import os

db = SQLAlchemy(settings_manager.database.host)

script_location = os.getcwd() + "/data/alembic/"
alembic = Alembic(db, script_location)
alembic.init(script_location)