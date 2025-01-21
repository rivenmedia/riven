import json
import os
from pathlib import Path

from program.settings.manager import SettingsManager

TEST_VERSION = "9.9.9"
DATA_PATH = Path(os.curdir) / "data"

# Sample old settings data
old_settings_data = {
    "version": "0.7.5",
    "debug": True,
    "log": True,
    "force_refresh": False,
    "map_metadata": True,
    "tracemalloc": False,
    "downloaders": {
        # "movie_filesize_min": 200,
        # "movie_filesize_max": -1,
        # "episode_filesize_min": 40,
        # "episode_filesize_max": -1,
        "real_debrid": {
            "enabled": False,
            "api_key": "",
            "proxy_enabled": False,
            "proxy_url": ""
        },
        "all_debrid": {
            "enabled": True,
            "api_key": "12345678",
            "proxy_enabled": False,
            "proxy_url": "https://no_proxy.com"
        },
    },
}


def test_load_and_migrate_settings():
    temp_settings_file = Path.joinpath(DATA_PATH, "settings.json")
    version_file = Path.joinpath(DATA_PATH, "VERSION")

    try:
        temp_settings_file.write_text(json.dumps(old_settings_data))
        version_file.write_text("9.9.9")

        import program.settings.models
        program.settings.manager.data_dir_path = DATA_PATH
        program.settings.models.version_file_path = version_file
        settings_manager = SettingsManager()

        assert settings_manager.settings.debug is True
        assert settings_manager.settings.log is True
        assert settings_manager.settings.force_refresh is False
        assert settings_manager.settings.map_metadata is True
        assert settings_manager.settings.tracemalloc is False
        # assert settings_manager.settings.downloaders.movie_filesize_min == 200
        assert settings_manager.settings.downloaders.real_debrid.enabled is False
        assert settings_manager.settings.downloaders.all_debrid.enabled is True
        assert settings_manager.settings.downloaders.all_debrid.api_key == "12345678"
        assert settings_manager.settings.downloaders.all_debrid.proxy_url == "https://no_proxy.com"
        assert settings_manager.settings.database.host == "postgresql+psycopg2://postgres:postgres@localhost/riven"
        assert settings_manager.settings.version == TEST_VERSION
    finally:
        temp_settings_file.unlink()
        version_file.unlink()