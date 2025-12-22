from sqla_wrapper import SQLAlchemy
from program.settings import settings_manager


engine_options = {
    "pool_size": 25,  # Prom: Set to 1 when debugging sql queries
    "max_overflow": 25,  # Prom: Set to 0 when debugging sql queries
    "pool_pre_ping": True,  # Prom: Set to False when debugging sql queries
    "pool_recycle": 1800,  # Prom: Set to -1 when debugging sql queries
    "echo": False,  # Prom: Set to true when debugging sql queries
}

db_host = str(settings_manager.settings.database.host)
db = SQLAlchemy(db_host, engine_options=engine_options)
