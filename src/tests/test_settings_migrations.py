"""Tests for settings migration functionality."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSettingsMigrations:
    """Test cases for settings migration functionality - completely isolated."""
    
    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary directory for test data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            # Ensure the temp directory is completely isolated
            assert not temp_path.exists() or temp_path.is_dir()
            yield temp_path
    
    @pytest.fixture(autouse=True)
    def isolate_settings_manager(self, temp_data_dir):
        """Ensure SettingsManager never touches real data directory."""
        # Safety check: ensure we're not using the real data directory
        real_data_dir = Path("/home/spoked/projects/riven/data")
        assert str(temp_data_dir) != str(real_data_dir), "Test must not use real data directory!"
        
        # Patch the data directory path to use our temp directory
        with patch("program.utils.data_dir_path", temp_data_dir):
            # Also patch any other potential paths
            with patch("program.settings.manager.data_dir_path", temp_data_dir):
                yield
    
    def test_default_settings_creation(self, temp_data_dir):
        """Test that default settings are created when no settings file exists."""
        # Import locally to avoid global settings_manager creation
        from program.settings.manager import SettingsManager
        from program.settings.models import AppModel
        
        settings_manager = SettingsManager()
        
        # Should create default settings
        assert isinstance(settings_manager.settings, AppModel)
        # Settings file should not exist yet (not saved automatically)
        assert not settings_manager.settings_file.exists()
        
        # Should have default values
        assert settings_manager.settings.debug is True  # Default is True
        assert settings_manager.settings.log is True
        assert settings_manager.settings.force_refresh is False
    
    def test_settings_loading_from_file(self, temp_data_dir):
        """Test loading settings from an existing file."""
        from program.settings.manager import SettingsManager

        # Create a settings file with test data
        settings_data = {
            "debug": True,
            "log": False,
            "force_refresh": True,
            "map_metadata": False,
            "tracemalloc": True,
            "downloaders": {
                "real_debrid": {
                    "enabled": True,
                    "api_key": "test_key_123"
                },
                "all_debrid": {
                    "enabled": False,
                    "api_key": ""
                }
            }
        }
        
        settings_file = temp_data_dir / "settings.json"
        settings_file.write_text(json.dumps(settings_data, indent=4))
        
        settings_manager = SettingsManager()
        
        # Should load the settings from file
        assert settings_manager.settings.debug is True
        assert settings_manager.settings.log is False
        assert settings_manager.settings.force_refresh is True
        assert settings_manager.settings.map_metadata is False
        assert settings_manager.settings.tracemalloc is True
        
        # Should load downloader settings
        assert settings_manager.settings.downloaders.real_debrid.enabled is True
        assert settings_manager.settings.downloaders.real_debrid.api_key == "test_key_123"
        
        assert settings_manager.settings.downloaders.all_debrid.enabled is False
        assert settings_manager.settings.downloaders.all_debrid.api_key == ""
    
    def test_settings_migration_with_missing_fields(self, temp_data_dir):
        """Test that missing fields are filled with defaults during migration."""
        from program.settings.manager import SettingsManager

        # Create settings with only some fields (simulating old version)
        old_settings_data = {
            "debug": True,
            "log": True,
            # Missing: force_refresh, map_metadata, tracemalloc, etc.
            "downloaders": {
                "real_debrid": {
                    "enabled": False,
                    "api_key": ""
                    # Missing: proxy_enabled, proxy_url
                }
                # Missing: all_debrid section entirely
            }
        }
        
        settings_file = temp_data_dir / "settings.json"
        settings_file.write_text(json.dumps(old_settings_data, indent=4))
        
        settings_manager = SettingsManager()
        
        # Should have the provided values
        assert settings_manager.settings.debug is True
        assert settings_manager.settings.log is True
        
        # Should have default values for missing fields
        assert settings_manager.settings.force_refresh is False  # Default
        assert settings_manager.settings.map_metadata is True   # Default
        assert settings_manager.settings.tracemalloc is False  # Default
        
        # Should have default values for missing downloader fields
        assert settings_manager.settings.downloaders.real_debrid.enabled is False
        assert settings_manager.settings.downloaders.real_debrid.api_key == ""
        
        # Should have default all_debrid section
        assert settings_manager.settings.downloaders.all_debrid.enabled is False  # Default
        assert settings_manager.settings.downloaders.all_debrid.api_key == ""      # Default
    
    def test_settings_save_and_reload(self, temp_data_dir):
        """Test that settings can be saved and reloaded correctly."""
        from program.settings.manager import SettingsManager

        # Create initial settings
        settings_manager = SettingsManager()
        
        # Modify some settings
        settings_manager.settings.debug = True
        settings_manager.settings.downloaders.real_debrid.enabled = True
        settings_manager.settings.downloaders.real_debrid.api_key = "new_key_456"
        
        # Save settings
        settings_manager.save()
        
        # Create new manager to reload
        settings_manager2 = SettingsManager()
        
        # Should have the saved values
        assert settings_manager2.settings.debug is True
        assert settings_manager2.settings.downloaders.real_debrid.enabled is True
        assert settings_manager2.settings.downloaders.real_debrid.api_key == "new_key_456"
    
    def test_environment_variable_override(self, temp_data_dir):
        """Test that environment variables can override settings."""
        from program.settings.manager import SettingsManager

        # Create a settings file with different values
        settings_data = {
            "debug": False,
            "log": True,
            "downloaders": {
                "real_debrid": {
                    "enabled": False,
                    "api_key": "file_key_123"
                }
            }
        }
        
        settings_file = temp_data_dir / "settings.json"
        settings_file.write_text(json.dumps(settings_data, indent=4))
        
        # Set environment variables that should override the file
        with patch.dict(os.environ, {
            "RIVEN_DEBUG": "true",
            "RIVEN_LOG": "false",
            "RIVEN_DOWNLOADERS_REAL_DEBRID_ENABLED": "true",
            "RIVEN_DOWNLOADERS_REAL_DEBRID_API_KEY": "env_key_789"
        }):
            settings_manager = SettingsManager()
            
            # Should use environment variable values (overriding file values)
            assert settings_manager.settings.debug is True  # From env, not file
            assert settings_manager.settings.log is False     # From env, not file
            assert settings_manager.settings.downloaders.real_debrid.enabled is True  # From env, not file
            assert settings_manager.settings.downloaders.real_debrid.api_key == "env_key_789"  # From env, not file
    
    def test_invalid_json_handling(self, temp_data_dir):
        """Test handling of invalid JSON in settings file."""
        from program.settings.manager import SettingsManager
        
        settings_file = temp_data_dir / "settings.json"
        settings_file.write_text("{ invalid json }")
        
        with pytest.raises(json.JSONDecodeError):
            SettingsManager()
    
    def test_validation_error_handling(self, temp_data_dir):
        """Test handling of validation errors in settings."""
        from program.settings.manager import SettingsManager

        # Create settings with invalid values
        invalid_settings_data = {
            "debug": "not_a_boolean",  # Should be boolean
            "downloaders": {
                "real_debrid": {
                    "enabled": "not_a_boolean"  # Should be boolean
                }
            }
        }
        
        settings_file = temp_data_dir / "settings.json"
        settings_file.write_text(json.dumps(invalid_settings_data, indent=4))
        
        with pytest.raises(Exception):  # Should raise validation error
            SettingsManager()


if __name__ == "__main__":
    pytest.main([__file__])
