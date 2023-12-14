"""Settings manager"""
from utils.logger import logger
import json
import os
import shutil

class SettingsManager:
    """Class that handles settings"""

    def __init__(self):
        self.filename = "data/settings.json"
        self.config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
        self.settings_file = os.path.join(self.config_dir, self.filename)
        self.settings = {}
        self.load()

    def load(self):
        """Load settings from file"""
        if not os.path.exists(self.settings_file):
            default_settings_path = os.path.join(os.path.dirname(__file__), "default_settings.json")
            shutil.copy(default_settings_path, self.settings_file)
            logger.debug("Settings file not found, using default settings")
        with open(self.settings_file, "r", encoding="utf-8") as file:
            self.settings = json.loads(file.read())
        logger.debug("Settings loaded from %s", self.settings_file)

    def save(self):
        """Save settings to file"""
        with open(self.settings_file, "w", encoding="utf-8") as file:
            json.dump(self.settings, file, indent=4)
        logger.debug("Settings saved to %s", self.settings_file)

    def get(self, key):
        """Get setting with key"""
        if key in self.settings:
            value = self.settings[key]
            logger.debug("Get (%s) returned: %s", key, value)
            return value
        return None

    def set(self, key, value):
        """Set setting value with key"""
        if key in self.settings:
            logger.debug("Setting (%s) to (%s)", key, value)
            self.settings[key] = value

    def get_all(self):
        """Return all settings"""
        return self.settings

settings_manager = SettingsManager()
