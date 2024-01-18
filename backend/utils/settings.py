"""Settings manager"""
from utils.observable import Observable
import json
import os
import shutil


class SettingsManager(Observable):
    """Class that handles settings"""

    def __init__(self):
        self.filename = "data/settings.json"
        self.config_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
        )
        self.settings_file = os.path.join(self.config_dir, self.filename)
        self.default_settings_file = os.path.join(
                os.path.dirname(__file__), "default_settings.json"
            )
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
            shutil.copy(self.default_settings_file, self.settings_file)
        with open(self.settings_file, "r", encoding="utf-8") as file:
            current_settings = json.loads(file.read())
        self.settings = self.check_settings(current_settings)
        self.save()
        self.notify_observers()

    def check_settings(self, current_settings):
        default_settings = None
        with open(self.default_settings_file, "r", encoding="utf-8") as file:
            default_settings = json.loads(file.read())
        if current_settings is None:
            current_settings = {}
        self.check_setting_keys(default_settings, current_settings)
        current_settings["version"] = default_settings["version"]
        return current_settings

    def check_setting_keys(self, default, user):
        for key, default_value in default.items():
            user_value = user.get(key, None)

            if user_value is None:
                user[key] = default_value
            elif isinstance(default_value, dict) and isinstance(user_value, dict):
                self.check_setting_keys(default_value, user_value)

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
