from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from program.symlink import Symlinker, SymlinkConfig
from utils.settings import settings_manager as settings


@pytest.fixture
def mock_settings_get():
    with patch("utils.settings.SettingsManager.get") as mock_get:
        yield mock_get


@pytest.fixture
def mock_logger():
    with patch("program.symlink.logger") as mock_log:
        yield mock_log


base_settings = {
    "host_path": "/abs/path",
    "container_path": "/abs/path",
    "symlink_path": "/abs/path",
}


@pytest.mark.parametrize(
    "path_settings,expected_error",
    [
        ({**base_settings, **{"host_path": "."}}, "set to the current directory"),
        ({**base_settings, **{"host_path": "rel/"}}, "not an absolute path"),
        (base_settings, "does not exist"),
    ],
)
def test_symlinker_validate_fails(
    mock_settings_get, mock_logger, path_settings, expected_error
):
    mock_settings_get.return_value = path_settings
    with pytest.raises(ValueError):
        symlinker = Symlinker()

        error_messages = [call.args[0] for call in mock_logger.error.call_args_list]
        assert any(expected_error in message for message in error_messages)
        assert not symlinker.initialized


def test_library_paths_exists(mock_settings_get, tmp_path):
    test_cases = [
        (
            {
                "host_path": tmp_path.parent,
                "symlink_path": tmp_path,
                "container_path": tmp_path.parent,
            },
            tmp_path,
        ),
        ({"host_path": tmp_path, "container_path": tmp_path}, tmp_path.parent),
    ]
    with patch("program.symlink.Path.is_dir") as mock_is_dir:
        mock_is_dir.return_value = True
        for path_settings, test_path in test_cases:
            mock_settings_get.return_value = path_settings
            symlinker = Symlinker()
            assert symlinker.create_initial_folders() == True
            for name, folder in symlinker.__dict__.items():
                if not name.startswith("library_path"):
                    continue
                assert str(test_path) in str(folder)
