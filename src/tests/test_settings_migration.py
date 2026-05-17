import json
import os
from pathlib import Path

from program.settings import SettingsManager

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
            "proxy_url": "",
        },
        "all_debrid": {
            "enabled": True,
            "api_key": "12345678",
            "proxy_enabled": False,
            "proxy_url": "https://no_proxy.com",
        },
    },
}


def test_load_and_migrate_settings(monkeypatch):
    temp_settings_file = Path.joinpath(DATA_PATH, "settings.json")
    DATA_PATH.mkdir(parents=True, exist_ok=True)

    try:
        temp_settings_file.write_text(json.dumps(old_settings_data))

        monkeypatch.setattr("program.settings.data_dir_path", DATA_PATH)
        monkeypatch.setattr(
            "program.settings.models.get_version", lambda: TEST_VERSION
        )
        settings_manager = SettingsManager()

        assert settings_manager.settings.tracemalloc is False
        assert settings_manager.settings.logging.enabled is True
        # assert settings_manager.settings.downloaders.movie_filesize_min == 200
        assert settings_manager.settings.downloaders.real_debrid.enabled is False
        assert settings_manager.settings.downloaders.all_debrid.enabled is True
        assert settings_manager.settings.downloaders.all_debrid.api_key == "12345678"
        assert str(settings_manager.settings.database.host) == (
            "postgresql+psycopg2://postgres:postgres@localhost/riven"
        )
        assert settings_manager.settings.version == TEST_VERSION
    finally:
        if temp_settings_file.exists():
            temp_settings_file.unlink()
