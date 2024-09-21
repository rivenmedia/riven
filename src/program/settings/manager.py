import json
import os

from program.settings.models import AppModel, Observable
from jsonschema import validate, ValidationError as JsonSchemaValidationError
from pydantic import ValidationError
from utils import data_dir_path
from loguru import logger


class SettingsManager:
    """Class that handles settings, ensuring they are validated against a Pydantic schema."""

    def __init__(self):
        self.schema = self.update_schema()
        self.observers = []
        self.filename = "settings.json"
        self.settings_file = data_dir_path / self.filename

        Observable.set_notify_observers(self.notify_observers)

        if not self.settings_file.exists():
            self.settings = AppModel()
            settings_dict = json.loads(self.settings.model_dump_json())
            settings_dict = self.check_environment(settings_dict, "RIVEN")
            validate(instance=settings_dict, schema=self.schema)
            self.settings = AppModel.model_validate(settings_dict)
            self.notify_observers()
        else:
            self.load()

    def register_observer(self, observer):
        self.observers.append(observer)

    def notify_observers(self):
        for observer in self.observers:
            observer()

    def check_environment(self, settings, prefix="", seperator="_"):
        checked_settings = {}
        for key, value in settings.items():
            if isinstance(value, dict):
                sub_checked_settings = self.check_environment(value, f"{prefix}{seperator}{key}")
                checked_settings[key] = (sub_checked_settings)
            else:
                environment_variable = f"{prefix}_{key}".upper()
                if os.getenv(environment_variable, None):
                    new_value = os.getenv(environment_variable)
                    if isinstance(value, bool):
                        checked_settings[key] = new_value.lower() == "true" or new_value == "1"
                    elif isinstance(value, int):
                        checked_settings[key] = int(new_value)
                    elif isinstance(value, float):
                        checked_settings[key] = float(new_value)
                    elif isinstance(value, list):
                        checked_settings[key] = json.loads(new_value)
                    else:
                        checked_settings[key] = new_value
                else:
                    checked_settings[key] = value
        return checked_settings

    def load(self, settings_dict: dict | None = None):
        """Load settings from file, validating against the JSON Schema."""
        try:
            if not settings_dict:
                with open(self.settings_file, "r", encoding="utf-8") as file:
                    settings_dict = json.loads(file.read())
                    if os.environ.get("RIVEN_FORCE_ENV", "false").lower() == "true":
                        settings_dict = self.check_environment(settings_dict, "RIVEN")
            
            # Validate against JSON Schema
            self.update_schema()
            validate(instance=settings_dict, schema=self.schema)
            self.settings = AppModel.model_validate(settings_dict)
            self.save()
        except JsonSchemaValidationError as e:
            logger.error(f"JSON Schema validation error: {e}")
            raise
        except ValidationError as e:
            logger.error(f"Pydantic validation error: {e}")
            for error in e.errors():
                if error['type'] == 'value_error':
                    logger.error(f"Field '{error['loc'][0]}': {error['msg']}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing settings file: {e}")
            raise
        except FileNotFoundError:
            logger.warning(f"Error loading settings: {self.settings_file} does not exist")
            raise
        self.notify_observers()

    def save(self):
        """Save settings to file, using Pydantic model for JSON serialization."""
        with open(self.settings_file, "w", encoding="utf-8") as file:
            file.write(self.settings.model_dump_json(indent=4))
        self.update_schema()

    def update_schema(self):
        self.schema = AppModel.model_json_schema()


settings_manager = SettingsManager()
