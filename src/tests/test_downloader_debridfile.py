"""Tests for downloader models."""

import pytest

from program.services.downloaders.models import (
    FILESIZE_EPISODE_CONSTRAINT,
    FILESIZE_MOVIE_CONSTRAINT,
    VALID_VIDEO_EXTENSIONS,
    DebridFile,
    InvalidDebridFileException,
)


class TestDebridFileFactory:
    """Test cases for DebridFile.create factory method."""

    def test_create_valid_movie_file(self):
        """Test creating a valid movie file."""
        result = DebridFile.create(
            filename="movie.mp4",
            filesize_bytes=1000_000_000,  # 1GB
            filetype="movie",
            file_id=123
        )
        
        assert result is not None
        assert result.filename == "movie.mp4"
        assert result.filesize == 1000_000_000
        assert result.file_id == 123

    def test_create_valid_episode_file(self):
        """Test creating a valid episode file."""
        result = DebridFile.create(
            filename="episode.mkv",
            filesize_bytes=500_000_000,  # 500MB
            filetype="episode",
            file_id=456
        )
        
        assert result is not None
        assert result.filename == "episode.mkv"
        assert result.filesize == 500_000_000
        assert result.file_id == 456

    def test_create_without_file_id(self):
        """Test creating a file without file_id."""
        result = DebridFile.create(
            filename="test.avi",
            filesize_bytes=800_000_000,  # 800MB (above 700MB minimum)
            filetype="movie"
        )
        
        assert result is not None
        assert result.filename == "test.avi"
        assert result.filesize == 800_000_000
        assert result.file_id is None

    def test_create_without_filesize_limit(self):
        """Test creating a file with filesize validation disabled."""
        # Test with a very large file that would normally be rejected
        result = DebridFile.create(
            filename="huge_movie.mp4",
            filesize_bytes=10_000_000_000,  # 10GB
            filetype="movie",
            limit_filesize=False
        )
        
        assert result is not None
        assert result.filename == "huge_movie.mp4"
        assert result.filesize == 10_000_000_000

    def test_create_with_path(self):
        """Test creating a file with path parameter."""
        result = DebridFile.create(
            path="/path/to/movie.mp4",
            filename="movie.mp4",
            filesize_bytes=1000_000_000,
            filetype="movie"
        )
        
        assert result is not None
        assert result.filename == "movie.mp4"

    def test_reject_sample_file(self):
        """Test that sample files are rejected."""
        with pytest.raises(InvalidDebridFileException, match="Skipping sample file"):
            DebridFile.create(
                filename="sample_movie.mp4",
                filesize_bytes=1000_000_000,
                filetype="movie"
            )

    def test_reject_sample_file_case_insensitive(self):
        """Test that sample files are rejected case-insensitively."""
        with pytest.raises(InvalidDebridFileException, match="Skipping sample file"):
            DebridFile.create(
                filename="SAMPLE_movie.mp4",
                filesize_bytes=1000_000_000,
                filetype="movie"
            )

    def test_reject_non_video_file(self):
        """Test that non-video files are rejected."""
        with pytest.raises(InvalidDebridFileException, match="Skipping non-video file"):
            DebridFile.create(
                filename="document.pdf",
                filesize_bytes=1000_000_000,
                filetype="movie"
            )

    def test_reject_invalid_video_extension(self):
        """Test that files with invalid video extensions are rejected."""
        with pytest.raises(InvalidDebridFileException, match="Skipping non-video file"):
            DebridFile.create(
                filename="movie.xyz",
                filesize_bytes=1000_000_000,
                filetype="movie"
            )

    def test_accept_all_valid_video_extensions(self):
        """Test that all valid video extensions are accepted."""
        for ext in VALID_VIDEO_EXTENSIONS:
            result = DebridFile.create(
                filename=f"test.{ext}",
                filesize_bytes=800_000_000,  # 800MB (above 700MB minimum)
                filetype="movie"
            )
            assert result is not None
            assert result.filename == f"test.{ext}"

    def test_reject_anime_specials_in_path(self):
        """Test that anime specials in path are rejected."""
        special_patterns = ["OVA", "NCED", "NCOP", "NC", "ED1", "OP1", "SP1"]
        
        for pattern in special_patterns:
            with pytest.raises(InvalidDebridFileException, match="Skipping anime special"):
                DebridFile.create(
                    path=f"/anime/{pattern}/episode.mp4",
                    filename="episode.mp4",
                    filesize_bytes=200_000_000,  # 200MB (above 100MB minimum)
                    filetype="episode"
                )

    def test_reject_anime_specials_case_insensitive(self):
        """Test that anime specials are rejected case-insensitively."""
        with pytest.raises(InvalidDebridFileException, match="Skipping anime special"):
            DebridFile.create(
                path="/anime/ova/episode.mp4",
                filename="episode.mp4",
                filesize_bytes=200_000_000,  # 200MB (above 100MB minimum)
                filetype="episode"
            )

    def test_accept_normal_anime_episodes(self):
        """Test that normal anime episodes are accepted."""
        result = DebridFile.create(
            path="/anime/episode_01.mp4",
            filename="episode_01.mp4",
            filesize_bytes=200_000_000,  # 200MB (above 100MB minimum)
            filetype="episode"
        )
        
        assert result is not None
        assert result.filename == "episode_01.mp4"

    def test_movie_filesize_too_small(self):
        """Test that movies below minimum filesize are rejected."""
        min_size_mb = FILESIZE_MOVIE_CONSTRAINT[0]  # 700MB
        filesize_bytes = (min_size_mb - 1) * 1_000_000  # 699MB
        
        with pytest.raises(InvalidDebridFileException, match="Skipping movie file.*filesize.*is outside the allowed range"):
            DebridFile.create(
                filename="small_movie.mp4",
                filesize_bytes=filesize_bytes,
                filetype="movie"
            )

    def test_movie_filesize_too_large(self):
        """Test that movies above maximum filesize are rejected."""
        max_size_mb = FILESIZE_MOVIE_CONSTRAINT[1]
        if max_size_mb != float("inf"):
            filesize_bytes = (max_size_mb + 1) * 1_000_000
            
            with pytest.raises(InvalidDebridFileException, match="Skipping movie file.*filesize.*is outside the allowed range"):
                DebridFile.create(
                    filename="large_movie.mp4",
                    filesize_bytes=filesize_bytes,
                    filetype="movie"
                )

    def test_movie_filesize_valid_range(self):
        """Test that movies within valid filesize range are accepted."""
        min_size_mb = FILESIZE_MOVIE_CONSTRAINT[0]  # 700MB
        
        # Test minimum size
        filesize_bytes = min_size_mb * 1_000_000  # 700MB
        result = DebridFile.create(
            filename="min_movie.mp4",
            filesize_bytes=filesize_bytes,
            filetype="movie"
        )
        assert result is not None
        
        # Test a size above minimum (since max is infinity)
        filesize_bytes = (min_size_mb + 100) * 1_000_000  # 800MB
        result = DebridFile.create(
            filename="large_movie.mp4",
            filesize_bytes=filesize_bytes,
            filetype="movie"
        )
        assert result is not None

    def test_episode_filesize_too_small(self):
        """Test that episodes below minimum filesize are rejected."""
        min_size_mb = FILESIZE_EPISODE_CONSTRAINT[0]  # 100MB
        filesize_bytes = (min_size_mb - 1) * 1_000_000  # 99MB
        
        with pytest.raises(InvalidDebridFileException, match="Skipping episode file.*filesize.*is outside the allowed range"):
            DebridFile.create(
                filename="small_episode.mp4",
                filesize_bytes=filesize_bytes,
                filetype="episode"
            )

    def test_episode_filesize_too_large(self):
        """Test that episodes above maximum filesize are rejected."""
        max_size_mb = FILESIZE_EPISODE_CONSTRAINT[1]
        if max_size_mb != float("inf"):
            filesize_bytes = (max_size_mb + 1) * 1_000_000
            
            with pytest.raises(InvalidDebridFileException, match="Skipping episode file.*filesize.*is outside the allowed range"):
                DebridFile.create(
                    filename="large_episode.mp4",
                    filesize_bytes=filesize_bytes,
                    filetype="episode"
                )

    def test_episode_filesize_valid_range(self):
        """Test that episodes within valid filesize range are accepted."""
        min_size_mb = FILESIZE_EPISODE_CONSTRAINT[0]  # 100MB
        
        # Test minimum size
        filesize_bytes = min_size_mb * 1_000_000  # 100MB
        result = DebridFile.create(
            filename="min_episode.mp4",
            filesize_bytes=filesize_bytes,
            filetype="episode"
        )
        assert result is not None
        
        # Test a size above minimum (since max is infinity)
        filesize_bytes = (min_size_mb + 100) * 1_000_000  # 200MB
        result = DebridFile.create(
            filename="large_episode.mp4",
            filesize_bytes=filesize_bytes,
            filetype="episode"
        )
        assert result is not None

    def test_show_filesize_constraints(self):
        """Test that show filesize constraints work like episodes."""
        min_size_mb = FILESIZE_EPISODE_CONSTRAINT[0]  # 100MB
        filesize_bytes = (min_size_mb - 1) * 1_000_000  # 99MB
        
        with pytest.raises(InvalidDebridFileException, match="Skipping episode file.*filesize.*is outside the allowed range"):
            DebridFile.create(
                filename="small_show.mp4",
                filesize_bytes=filesize_bytes,
                filetype="show"
            )

    def test_season_filesize_constraints(self):
        """Test that season filesize constraints work like episodes."""
        min_size_mb = FILESIZE_EPISODE_CONSTRAINT[0]  # 100MB
        filesize_bytes = (min_size_mb - 1) * 1_000_000  # 99MB
        
        with pytest.raises(InvalidDebridFileException, match="Skipping episode file.*filesize.*is outside the allowed range"):
            DebridFile.create(
                filename="small_season.mp4",
                filesize_bytes=filesize_bytes,
                filetype="season"
            )

    def test_filesize_constraints_with_zero_bytes(self):
        """Test filesize constraints with zero bytes."""
        with pytest.raises(InvalidDebridFileException, match="Skipping movie file.*filesize.*is outside the allowed range"):
            DebridFile.create(
                filename="zero_movie.mp4",
                filesize_bytes=0,
                filetype="movie"
            )

    def test_multiple_validation_failures(self):
        """Test that the first validation failure is raised."""
        # This should fail on sample file check before filesize check
        with pytest.raises(InvalidDebridFileException, match="Skipping sample file"):
            DebridFile.create(
                filename="sample_movie.mp4",
                filesize_bytes=0,  # This would also fail filesize check
                filetype="movie"
            )

    def test_to_dict_method(self):
        """Test the to_dict method."""
        debrid_file = DebridFile(
            filename="test.mp4",
            filesize=100_000_000,
            file_id=123
        )
        
        result = debrid_file.to_dict()
        expected = {
            "filename": "test.mp4",
            "filesize": 100_000_000,
            "file_id": 123
        }
        
        assert result == expected

    def test_to_dict_with_none_values(self):
        """Test the to_dict method with None values."""
        debrid_file = DebridFile()
        
        result = debrid_file.to_dict()
        expected = {
            "filename": None,
            "filesize": None,
            "file_id": None
        }
        
        assert result == expected


class TestDebridFileEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_filename(self):
        """Test behavior with empty filename."""
        with pytest.raises(InvalidDebridFileException, match="Skipping non-video file"):
            DebridFile.create(
                filename="",
                filesize_bytes=100_000_000,
                filetype="movie"
            )

    def test_none_filename(self):
        """Test behavior with None filename."""
        with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'lower'"):
            DebridFile.create(
                filename=None,
                filesize_bytes=100_000_000,
                filetype="movie"
            )

    def test_filename_with_multiple_dots(self):
        """Test filename with multiple dots."""
        result = DebridFile.create(
            filename="movie.special.edition.mp4",
            filesize_bytes=800_000_000,  # 800MB (above 700MB minimum)
            filetype="movie"
        )
        assert result is not None
        assert result.filename == "movie.special.edition.mp4"

    def test_filename_with_uppercase_extension(self):
        """Test filename with uppercase extension."""
        result = DebridFile.create(
            filename="movie.MP4",
            filesize_bytes=800_000_000,  # 800MB (above 700MB minimum)
            filetype="movie"
        )
        assert result is not None
        assert result.filename == "movie.MP4"

    def test_anime_specials_in_middle_of_path(self):
        """Test anime specials pattern in middle of path."""
        with pytest.raises(InvalidDebridFileException, match="Skipping anime special"):
            DebridFile.create(
                path="/anime/series/OVA/special.mp4",
                filename="special.mp4",
                filesize_bytes=200_000_000,  # 200MB (above 100MB minimum)
                filetype="episode"
            )

    def test_anime_specials_partial_match(self):
        """Test that partial matches of anime specials are not rejected."""
        # These should NOT be rejected as they're not exact matches
        valid_names = ["november.mp4", "operation.mp4", "special_ops.mp4"]
        
        for name in valid_names:
            result = DebridFile.create(
                path=f"/anime/{name}",
                filename=name,
                filesize_bytes=200_000_000,  # 200MB (above 100MB minimum)
                filetype="episode"
            )
            assert result is not None
