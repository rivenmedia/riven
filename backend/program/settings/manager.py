from utils.observable import Observable
import json
import os
import shutil
from .models import Schema

class SettingsManager(Observable):
    """Class that handles settings"""

    def __init__(self):
        self.filename = "data/settings.json"
        self.config_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
        )
        self.settings_file = os.path.join(self.config_dir, self.filename)
        self.schema = Schema()
        self.settings = {}
        self.observers = []
        self.load()

    def register_observer(self, observer):
        self.observers.append(observer)

    def notify_observers(self):
        for observer in self.observers:
            observer.notify()

    def load(self):
        """Load settings from file"""
        if not os.path.exists(self.settings_file):
            for config in Schema():
                data = config.dict()
                self.settings[]
            default_settings_path = os.path.join(
                os.path.dirname(__file__), "default_settings.json"
            )
            shutil.copy(default_settings_path, self.settings_file)
        with open(self.settings_file, "r", encoding="utf-8") as file:
            self.settings = json.loads(file.read())
        self.notify_observers()

    def save(self):
        """Save settings to file"""
        with open(self.settings_file, "w", encoding="utf-8") as file:
            json.dump(self.settings, file, indent=4)

    def get(self, key):
        """Get setting with key"""
        return _get_nested_attr(self.settings, key)

    def set(self, data):
        """Set setting value with key"""
        for setting in data:
            _set_nested_attr(self.settings, setting.key, setting.value)
        self.notify_observers()

    def get_all(self):
        """Return all settings"""
        return self.settings

def _get_nested_attr(obj, key):
    if "." in key:
        parts = key.split(".", 1)
        current_key, rest_of_keys = parts[0], parts[1]

        if not obj.get(current_key, None):
            return None

        current_obj = obj.get(current_key)
        return _get_nested_attr(current_obj, rest_of_keys)
    else:
        return obj.get(key, None)


def _set_nested_attr(obj, key, value):
    if "." in key:
        parts = key.split(".", 1)
        current_key, rest_of_keys = parts[0], parts[1]

        if not obj.get(current_key):
            return False

        current_obj = obj.get(current_key)
        return _set_nested_attr(current_obj, rest_of_keys, value)
    else:
        obj[key] = value
        return True


settings_manager = SettingsManager()
