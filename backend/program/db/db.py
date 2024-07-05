from sqla_wrapper import Alembic, SQLAlchemy
from program.settings.manager import settings_manager
import os

db = SQLAlchemy(settings_manager.database.host)

script_location = os.getcwd() + "/data/alembic/"
alembic = Alembic(db, script_location)
alembic.init(script_location)

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

# https://stackoverflow.com/questions/61374525/how-do-i-check-if-alembic-migrations-need-to-be-generated
def need_upgrade_check() -> bool:
    diff = []
    with db.engine.connect() as connection:
        mc = MigrationContext.configure(connection)
        diff = compare_metadata(mc, db.Model.metadata)
    return diff != []

def run_migrations() -> None:
    if need_upgrade_check:
        alembic.revision("auto-upg")
        alembic.upgrade()