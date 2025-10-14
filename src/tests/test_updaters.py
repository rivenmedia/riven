"""Test suite for updater services"""

import os
from unittest.mock import MagicMock, Mock, patch

import pytest

from program.media.item import Episode, Movie, Season, Show
from program.services.updaters import Updater
from program.services.updaters.emby import EmbyUpdater
from program.services.updaters.jellyfin import JellyfinUpdater
from program.services.updaters.plex import PlexUpdater


# Fixtures for test media items
@pytest.fixture
def mock_movie():
    """Create a mock movie with filesystem entry"""
    movie = Mock(spec=Movie)
    movie.type = "movie"
    movie.filesystem_entry = Mock()
    movie.filesystem_entry.path = "/movies/Test Movie (2020)/Test Movie (2020).mkv"
    movie.updated = False
    movie.log_string = "Test Movie (2020)"
    return movie


@pytest.fixture
def mock_episode():
    """Create a mock episode with filesystem entry"""
    episode = Mock(spec=Episode)
    episode.type = "episode"
    episode.filesystem_entry = Mock()
    episode.filesystem_entry.path = "/shows/Test Show/Season 01/Test Show S01E01.mkv"
    episode.updated = False
    episode.log_string = "Test Show S01E01"
    return episode


@pytest.fixture
def mock_show():
    """Create a mock show with season and episode"""
    show = Mock(spec=Show)
    show.type = "show"
    show.filesystem_entry = Mock()
    show.filesystem_entry.path = "/shows/Test Show/Season 01/Test Show S01E01.mkv"
    show.updated = False
    show.log_string = "Test Show"
    return show


@pytest.fixture
def mock_settings():
    """Mock settings manager"""
    with patch(
        "program.services.updaters.plex.settings_manager"
    ) as mock_plex_settings, patch(
        "program.services.updaters.emby.settings_manager"
    ) as mock_emby_settings, patch(
        "program.services.updaters.jellyfin.settings_manager"
    ) as mock_jellyfin_settings, patch(
        "program.services.updaters.settings_manager"
    ) as mock_main_settings:

        # Plex settings
        mock_plex_settings.settings.updaters.plex.enabled = False
        mock_plex_settings.settings.updaters.plex.token = "test_token"
        mock_plex_settings.settings.updaters.plex.url = "http://localhost:32400"
        mock_plex_settings.settings.updaters.library_path = "/mnt/library"

        # Emby settings
        mock_emby_settings.settings.updaters.emby.enabled = False
        mock_emby_settings.settings.updaters.emby.api_key = "test_api_key"
        mock_emby_settings.settings.updaters.emby.url = "http://localhost:8096"

        # Jellyfin settings
        mock_jellyfin_settings.settings.updaters.jellyfin.enabled = False
        mock_jellyfin_settings.settings.updaters.jellyfin.api_key = "test_api_key"
        mock_jellyfin_settings.settings.updaters.jellyfin.url = "http://localhost:8097"

        # Main updater settings
        mock_main_settings.settings.updaters.library_path = "/mnt/library"

        yield {
            "plex": mock_plex_settings,
            "emby": mock_emby_settings,
            "jellyfin": mock_jellyfin_settings,
            "main": mock_main_settings,
        }


# PlexUpdater Tests
class TestPlexUpdater:
    """Test suite for PlexUpdater"""

    def test_initialization_disabled(self, mock_settings):
        """Test that PlexUpdater doesn't initialize when disabled"""
        updater = PlexUpdater()
        assert not updater.initialized
        assert updater.service_name == "Plex"

    def test_initialization_enabled(self, mock_settings):
        """Test that PlexUpdater initializes when enabled and configured"""
        mock_settings["plex"].settings.updaters.plex.enabled = True

        with patch("program.services.updaters.plex.di") as mock_di:
            mock_api = Mock()
            mock_api.validate_server.return_value = True
            mock_api.map_sections_with_paths.return_value = {}
            mock_di.__getitem__.return_value = mock_api

            updater = PlexUpdater()
            assert updater.initialized

    def test_refresh_path_success(self, mock_settings):
        """Test successful path refresh"""
        mock_settings["plex"].settings.updaters.plex.enabled = True

        with patch("program.services.updaters.plex.di") as mock_di:
            mock_api = Mock()
            mock_api.validate_server.return_value = True

            # Create mock section
            mock_section = Mock()
            mock_section.key = "1"
            mock_section.title = "Movies"
            mock_section.type = "movie"
            mock_section.locations = ["/mnt/library/movies"]

            mock_api.map_sections_with_paths.return_value = {
                mock_section: ["/mnt/library/movies"]
            }
            mock_api.update_section.return_value = True
            mock_di.__getitem__.return_value = mock_api

            updater = PlexUpdater()
            result = updater.refresh_path("/mnt/library/movies/Test Movie (2020)")

            assert result is True
            mock_api.update_section.assert_called_once_with(
                mock_section, "/mnt/library/movies/Test Movie (2020)"
            )

    def test_refresh_path_no_matching_section(self, mock_settings):
        """Test refresh_path when no section matches the path"""
        mock_settings["plex"].settings.updaters.plex.enabled = True

        with patch("program.services.updaters.plex.di") as mock_di:
            mock_api = Mock()
            mock_api.validate_server.return_value = True
            mock_api.map_sections_with_paths.return_value = {}
            mock_di.__getitem__.return_value = mock_api

            updater = PlexUpdater()
            result = updater.refresh_path("/mnt/library/movies/Test Movie (2020)")

            assert result is False


# EmbyUpdater Tests
class TestEmbyUpdater:
    """Test suite for EmbyUpdater"""

    def test_initialization_disabled(self, mock_settings):
        """Test that EmbyUpdater doesn't initialize when disabled"""
        updater = EmbyUpdater()
        assert not updater.initialized
        assert updater.service_name == "Emby"

    def test_initialization_enabled(self, mock_settings):
        """Test that EmbyUpdater initializes when enabled"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        with patch.object(EmbyUpdater, "validate", return_value=True):
            updater = EmbyUpdater()
            assert updater.initialized

    def test_refresh_path_success(self, mock_settings):
        """Test successful path refresh"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        updater = EmbyUpdater()

        # Mock the session.post call
        with patch.object(updater.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.ok = True
            mock_post.return_value = mock_response

            result = updater.refresh_path("/mnt/library/movies/Test Movie (2020)")

            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/Library/Media/Updated" in call_args[0][0]
            assert (
                call_args[1]["json"]["Updates"][0]["Path"]
                == "/mnt/library/movies/Test Movie (2020)"
            )

    def test_refresh_path_failure(self, mock_settings):
        """Test failed path refresh"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        updater = EmbyUpdater()

        with patch.object(updater.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.ok = False
            mock_post.return_value = mock_response

            result = updater.refresh_path("/mnt/library/movies/Test Movie (2020)")

            assert result is False


# JellyfinUpdater Tests
class TestJellyfinUpdater:
    """Test suite for JellyfinUpdater"""

    def test_initialization_disabled(self, mock_settings):
        """Test that JellyfinUpdater doesn't initialize when disabled"""
        updater = JellyfinUpdater()
        assert not updater.initialized
        assert updater.service_name == "Jellyfin"

    def test_initialization_enabled(self, mock_settings):
        """Test that JellyfinUpdater initializes when enabled"""
        mock_settings["jellyfin"].settings.updaters.jellyfin.enabled = True

        with patch.object(JellyfinUpdater, "validate", return_value=True):
            updater = JellyfinUpdater()
            assert updater.initialized

    def test_refresh_path_ignores_path(self, mock_settings):
        """Test that Jellyfin refresh ignores the path parameter"""
        mock_settings["jellyfin"].settings.updaters.jellyfin.enabled = True

        updater = JellyfinUpdater()

        with patch.object(updater.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.ok = True
            mock_post.return_value = mock_response

            result = updater.refresh_path("/any/path/here")

            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/Library/Refresh" in call_args[0][0]

    def test_refresh_path_failure(self, mock_settings):
        """Test failed library refresh"""
        mock_settings["jellyfin"].settings.updaters.jellyfin.enabled = True

        updater = JellyfinUpdater()

        with patch.object(updater.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.ok = False
            mock_post.return_value = mock_response

            result = updater.refresh_path("/any/path")

            assert result is False


# Main Updater Tests
class TestUpdater:
    """Test suite for main Updater class"""

    def test_initialization(self, mock_settings):
        """Test Updater initialization"""
        updater = Updater()
        assert updater.key == "updater"
        assert updater.library_path == "/mnt/library"
        assert PlexUpdater in updater.services
        assert EmbyUpdater in updater.services
        assert JellyfinUpdater in updater.services

    def test_validate_no_services(self, mock_settings):
        """Test validation when no services are initialized"""
        updater = Updater()
        # All services disabled by default in mock_settings
        assert not updater.initialized

    def test_validate_with_services(self, mock_settings):
        """Test validation when at least one service is initialized"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        with patch.object(EmbyUpdater, "validate", return_value=True):
            updater = Updater()
            assert updater.initialized

    def test_run_movie_extracts_correct_path(self, mock_settings, mock_movie):
        """Test that run() extracts correct path for movies (parent directory)"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        with patch.object(EmbyUpdater, "validate", return_value=True):
            updater = Updater()

            with patch.object(updater, "refresh_path") as mock_refresh:
                list(updater.run(mock_movie))

                # For movies, should refresh parent directory
                expected_path = "/mnt/library/movies/Test Movie (2020)"
                mock_refresh.assert_called_once_with(expected_path)
                assert mock_movie.updated is True

    def test_run_episode_extracts_correct_path(self, mock_settings, mock_episode):
        """Test that run() extracts correct path for episodes (parent's parent directory)"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        with patch.object(EmbyUpdater, "validate", return_value=True):
            updater = Updater()

            with patch.object(updater, "refresh_path") as mock_refresh:
                list(updater.run(mock_episode))

                # For episodes, should refresh parent's parent (show folder, not season)
                expected_path = "/mnt/library/shows/Test Show"
                mock_refresh.assert_called_once_with(expected_path)
                assert mock_episode.updated is True

    def test_run_no_filesystem_entry(self, mock_settings, mock_movie):
        """Test run() when item has no filesystem entry"""
        mock_settings["emby"].settings.updaters.emby.enabled = True
        mock_movie.filesystem_entry = None

        with patch.object(EmbyUpdater, "validate", return_value=True):
            updater = Updater()

            with patch.object(updater, "refresh_path") as mock_refresh:
                list(updater.run(mock_movie))

                # Should not call refresh_path
                mock_refresh.assert_not_called()

    def test_run_not_initialized(self, mock_settings, mock_movie):
        """Test run() when updater is not initialized"""
        updater = Updater()
        assert not updater.initialized

        with patch.object(updater, "refresh_path") as mock_refresh:
            list(updater.run(mock_movie))

            # Should not call refresh_path
            mock_refresh.assert_not_called()

    def test_refresh_path_calls_all_services(self, mock_settings):
        """Test that refresh_path calls all initialized services"""
        mock_settings["emby"].settings.updaters.emby.enabled = True
        mock_settings["jellyfin"].settings.updaters.jellyfin.enabled = True

        with patch.object(EmbyUpdater, "validate", return_value=True), patch.object(
            JellyfinUpdater, "validate", return_value=True
        ):
            updater = Updater()

            # Mock the service refresh_path methods
            for service in updater.services.values():
                service.refresh_path = Mock(return_value=True)

            result = updater.refresh_path("/test/path")

            assert result is True
            # Check that initialized services were called
            for service in updater.services.values():
                if service.initialized:
                    service.refresh_path.assert_called_once_with("/test/path")

    def test_refresh_path_handles_service_failure(self, mock_settings):
        """Test that refresh_path handles service failures gracefully"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        updater = Updater()

        # Mock service to raise exception
        for service in updater.services.values():
            if service.initialized:
                service.refresh_path = Mock(side_effect=Exception("Test error"))

        # Should not raise exception
        result = updater.refresh_path("/test/path")
        assert result is False

    def test_refresh_path_returns_true_if_any_succeeds(self, mock_settings):
        """Test that refresh_path returns True if at least one service succeeds"""
        mock_settings["emby"].settings.updaters.emby.enabled = True
        mock_settings["jellyfin"].settings.updaters.jellyfin.enabled = True

        with patch.object(EmbyUpdater, "validate", return_value=True), patch.object(
            JellyfinUpdater, "validate", return_value=True
        ):
            updater = Updater()

            # Mock services: one succeeds, one fails
            services_list = list(updater.services.values())
            services_list[0].refresh_path = Mock(return_value=False)
            services_list[1].refresh_path = Mock(return_value=True)

            result = updater.refresh_path("/test/path")
            assert result is True


# Integration Tests
class TestUpdaterIntegration:
    """Integration tests for updater workflow"""

    def test_movie_workflow(self, mock_settings, mock_movie):
        """Test complete workflow for updating a movie"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        with patch.object(EmbyUpdater, "validate", return_value=True):
            updater = Updater()

            # Mock Emby service
            emby_service = updater.services[EmbyUpdater]
            with patch.object(emby_service.session, "post") as mock_post:
                mock_response = Mock()
                mock_response.ok = True
                mock_post.return_value = mock_response

                # Run the updater
                result = list(updater.run(mock_movie))

                # Verify item was returned and updated
                assert len(result) == 1
                assert result[0] == mock_movie
                assert mock_movie.updated is True

                # Verify Emby was called with correct path
                mock_post.assert_called_once()
                call_args = mock_post.call_args
                assert (
                    call_args[1]["json"]["Updates"][0]["Path"]
                    == "/mnt/library/movies/Test Movie (2020)"
                )

    def test_show_workflow(self, mock_settings, mock_show):
        """Test complete workflow for updating a show"""
        mock_settings["emby"].settings.updaters.emby.enabled = True

        with patch.object(EmbyUpdater, "validate", return_value=True):
            updater = Updater()

            # Mock Emby service
            emby_service = updater.services[EmbyUpdater]
            with patch.object(emby_service.session, "post") as mock_post:
                mock_response = Mock()
                mock_response.ok = True
                mock_post.return_value = mock_response

                # Run the updater
                result = list(updater.run(mock_show))

                # Verify show was returned and updated
                assert len(result) == 1
                assert result[0] == mock_show
                assert mock_show.updated is True

                # Verify Emby was called with show folder (not season folder)
                mock_post.assert_called_once()
                call_args = mock_post.call_args
                assert (
                    call_args[1]["json"]["Updates"][0]["Path"]
                    == "/mnt/library/shows/Test Show"
                )
