import json
import os
import shutil
from pathlib import Path

from pydantic import ValidationError

from utils import data_dir_path
from program.settings.models import AppModel
from utils.logger import logger
from utils.observable import Observable


class SettingsManager(Observable):
    """Class that handles settings, ensuring they are validated against a Pydantic schema."""

    def __init__(self):
        self.observers = []
        self.filename = "settings.json"
        self.settings_file = data_dir_path / self.filename

        AppModel.set_notify_observers(self.notify_observers)

        if not os.path.exists(self.settings_file):
            self.settings = AppModel()
            self.notify_observers()
        else:
            self.load()

    def register_observer(self, observer):
        self.observers.append(observer)

    def notify_observers(self):
        for observer in self.observers:
            observer.notify()

    def load(self, settings_dict: dict = None):
        """Load settings from file, validating against the AppModel schema."""
        try:
            if not settings_dict:
                with open(self.settings_file, "r", encoding="utf-8") as file:
                    settings_dict = json.loads(file.read())
            self.settings = AppModel.model_validate(settings_dict)
        except ValidationError as e:
            logger.error(f"Error loading settings: {e}, initializing with default settings")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing settings file: {e}, initializing with default settings")
            raise
        except FileNotFoundError as e:
            logger.error(f"Error loading settings: {self.settings_file} does not exist")
            raise
        self.notify_observers()
        
    def save(self):
        """Save settings to file, using Pydantic model for JSON serialization."""
        with open(self.settings_file, "w", encoding="utf-8") as file:
            file.write(self.settings.model_dump_json(indent=4))
            


settings_manager = SettingsManager()