"""Tests for multiple subtitle downloads per language functionality."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from types import SimpleNamespace


class TestSubliminalMultipleDownloads:
    """Test cases for downloading multiple subtitles per language."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        settings = Mock()
        settings.post_processing.subliminal.enabled = True
        settings.post_processing.subliminal.languages = ["eng", "jpn", "ger"]
        settings.post_processing.subliminal.count_per_language = 2
        settings.post_processing.subliminal.providers = {}
        return settings

    @pytest.fixture
    def mock_video(self):
        """Create a mock video object."""
        video = Mock()
        video.name = "test_movie.mkv"
        video.symlink_path = "/tmp/test_movie.mkv"
        return video

    @pytest.fixture
    def mock_subtitles(self):
        """Create mock subtitles with different scores."""
        subtitles = []
        
        # English subtitles
        for i, score in enumerate([10, 8, 5, 3]):
            sub = Mock()
            sub.language = Mock()
            sub.language.__str__ = Mock(return_value="eng")
            sub.language.__eq__ = lambda self, other: str(self) == str(other)
            sub.get_matches = Mock(return_value=['match'] * score)
            subtitles.append(sub)
        
        # German subtitles
        for i, score in enumerate([9, 7, 4]):
            sub = Mock()
            sub.language = Mock()
            sub.language.__str__ = Mock(return_value="ger")
            sub.language.__eq__ = lambda self, other: str(self) == str(other)
            sub.get_matches = Mock(return_value=['match'] * score)
            subtitles.append(sub)
        
        # Japanese subtitles
        for i, score in enumerate([6, 2]):
            sub = Mock()
            sub.language = Mock()
            sub.language.__str__ = Mock(return_value="jpn")
            sub.language.__eq__ = lambda self, other: str(self) == str(other)
            sub.get_matches = Mock(return_value=['match'] * score)
            subtitles.append(sub)
        
        return subtitles

    @patch('program.services.post_processing.subliminal.settings_manager')
    @patch('program.services.post_processing.subliminal.ProviderPool')
    @patch('program.services.post_processing.subliminal.Video')
    @patch('program.services.post_processing.subliminal.save_subtitles')
    @patch('program.services.post_processing.subliminal.get_existing_subtitles')
    def test_download_multiple_subtitles_per_language(
        self, mock_get_existing, mock_save, mock_video_class, 
        mock_pool_class, mock_settings_manager, mock_settings, 
        mock_video, mock_subtitles
    ):
        """Test downloading multiple subtitles per language."""
        # Setup
        mock_settings_manager.settings = mock_settings
        mock_video_class.fromname.return_value = mock_video
        mock_get_existing.return_value = set()
        
        # Configure pool
        mock_pool = Mock()
        mock_pool.list_subtitles.return_value = mock_subtitles
        mock_pool.download_subtitles.return_value = None
        mock_pool_class.return_value = mock_pool
        
        # Import and initialize after mocks are set up
        from program.services.post_processing.subliminal import Subliminal
        
        subliminal = Subliminal()
        subliminal.pool = mock_pool
        subliminal.languages = {Mock(code=lang) for lang in ["eng", "jpn", "ger"]}
        
        # Create mock item
        item = Mock()
        item.type = "movie"
        item.symlink_path = "/tmp/test_movie.mkv"
        
        # Execute
        video, selected_subtitles = subliminal.get_subtitles(item)
        
        # Verify
        assert len(selected_subtitles) == 6  # 2 per language * 3 languages
        
        # Check that we got the top 2 for each language
        eng_subs = [s for s in selected_subtitles if str(s.language) == "eng"]
        ger_subs = [s for s in selected_subtitles if str(s.language) == "ger"]
        jpn_subs = [s for s in selected_subtitles if str(s.language) == "jpn"]
        
        assert len(eng_subs) == 2
        assert len(ger_subs) == 2
        assert len(jpn_subs) == 2
        
        # Verify they are the highest scoring ones
        assert len(eng_subs[0].get_matches(mock_video)) >= len(eng_subs[1].get_matches(mock_video))
        assert len(ger_subs[0].get_matches(mock_video)) >= len(ger_subs[1].get_matches(mock_video))

    @patch('program.services.post_processing.subliminal.settings_manager')
    @patch('program.services.post_processing.subliminal.save_subtitles')
    @patch('program.services.post_processing.subliminal.pathlib.Path')
    def test_save_multiple_subtitles_with_correct_naming(
        self, mock_path, mock_save, mock_settings_manager, mock_settings
    ):
        """Test that multiple subtitles are saved with correct filenames."""
        # Setup
        mock_settings_manager.settings = mock_settings
        
        from program.services.post_processing.subliminal import Subliminal
        
        subliminal = Subliminal()
        
        # Create mock video and subtitles
        mock_video = Mock()
        mock_video.name = Mock()
        mock_video.name.stem = "test_movie"
        mock_video.name.parent = "/tmp"
        
        # Create subtitles - 2 for each language
        subtitles = []
        for lang in ["eng", "ger"]:
            for i in range(2):
                sub = Mock()
                sub.language = Mock()
                sub.language.__str__ = Mock(return_value=lang)
                subtitles.append(sub)
        
        # Execute
        subliminal.save_subtitles(mock_video, subtitles, Mock())
        
        # Verify save_subtitles was called correctly
        assert mock_save.call_count == 4
        
        # Check that the second subtitle of each language has a custom filename
        calls = mock_save.call_args_list
        
        # First subtitle of each language should use default naming
        assert calls[0][1].get('filename') is None
        assert calls[2][1].get('filename') is None
        
        # Second subtitle of each language should have numbered filename
        assert calls[1][1]['filename'] == "test_movie.eng.2.srt"
        assert calls[3][1]['filename'] == "test_movie.heb.2.srt"

    @patch('program.services.post_processing.subliminal.settings_manager')
    def test_backward_compatibility_single_subtitle(
        self, mock_settings_manager, mock_settings
    ):
        """Test that count_per_language=1 maintains backward compatibility."""
        # Setup with count_per_language = 1
        mock_settings.post_processing.subliminal.count_per_language = 1
        mock_settings_manager.settings = mock_settings
        
        # Rest of the test would verify only 1 subtitle per language is downloaded
        # Similar structure to the multiple download test but asserting count = 1 