import json
import os

from program.settings.models import AppModel, Observable
from pydantic import ValidationError
from utils import data_dir_path
from utils.logger import logger


class SettingsManager:
    """Class that handles settings, ensuring they are validated against a Pydantic schema."""

    def __init__(self):
        self.observers = []
        self.filename = "settings.json"
        self.settings_file = data_dir_path / self.filename

        Observable.set_notify_observers(self.notify_observers)

        if not self.settings_file.exists():
            self.settings = AppModel()
            self.settings = self.check_environment(json.loads(self.settings.model_dump_json()), "RIVEN")
            self.notify_observers()
        else:
            self.load()

    def register_observer(self, observer):
        self.observers.append(observer)

    def notify_observers(self):
        for observer in self.observers:
            observer()

    def load_settings_file(self):
        with open(self.settings_file, "r", encoding="utf-8") as file:
            return json.loads(file.read())
    def save_settings_string(self):
        return self.settings.model_dump_json()
    
    def check_environment(self, settings, prefix="", seperator="_"):
        checked_settings = {}
        for key, value in settings.items():
            if isinstance(value, dict):
                sub_checked_settings = self.check_environment(value, f"{prefix}{seperator}{key}")
                checked_settings[key] = (sub_checked_settings)
            else:
                environment_variable = f"{prefix}_{key}".upper()
                if os.getenv(environment_variable, None):
                    print(f"Found the following environment variable: {environment_variable}")
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
        """Load settings from file, validating against the AppModel schema."""
        try:
            if not settings_dict:
                with open(self.settings_file, "r", encoding="utf-8") as file:
                    settings_dict = json.loads(file.read())
                    if os.environ["RIVEN_FORCE_ENV"]:
                        settings_dict = self.check_environment(settings_dict, "RIVEN")
            self.settings = AppModel.model_validate(settings_dict)
        except ValidationError as e:
            logger.error(
                f"Error validating settings: {e}"
            )
            raise
        except json.JSONDecodeError as e:
            logger.error(
                f"Error parsing settings file: {e}"
            )
            raise
        except FileNotFoundError:
            logger.warning(f"Error loading settings: {self.settings_file} does not exist")
            raise
        self.notify_observers()

    def save(self):
        """Save settings to file, using Pydantic model for JSON serialization."""
        with open(self.settings_file, "w", encoding="utf-8") as file:
            file.write(self.settings.model_dump_json(indent=4))


settings_manager = SettingsManager()
