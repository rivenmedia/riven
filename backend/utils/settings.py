"""Settings manager"""
from utils.logger import logger
import json
import os
import shutil

class SettingsManager:
    """Class that handles settings"""

    def __init__(self):
        self.filename = "settings.json"
        self.config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
        self.settings_file = os.path.join(self.config_dir, self.filename)
        self.settings = {}
        self.load()

    def load(self):
        """Load settings from file"""
        if not os.path.exists(os.path.join(self.config_dir, self.filename)):
            shutil.copy(os.path.join(os.path.dirname(__file__), "default_settings.json"), os.path.join(self.config_dir, self.filename))
            logger.debug("Settings file not found, using default settings")
        with open(self.filename, "r", encoding="utf-8") as file:
            self.settings = json.loads(file.read())
        logger.debug("Settings loaded from %s", self.filename)

    def save(self):
        """Save settings to file"""
        with open(self.filename, "w", encoding="utf-8") as file:
            json.dump(self.settings, file, indent=4)
        logger.debug("Settings saved to %s", self.filename)

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
