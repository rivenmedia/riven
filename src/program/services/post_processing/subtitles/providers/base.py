"""
Base provider interface for subtitle providers.
"""

from abc import ABC, abstractmethod
from typing import Any


class SubtitleProvider(ABC):
    """Abstract base class for subtitle providers."""

    @abstractmethod
    def search_subtitles(
        self,
        imdb_id: str,
        video_hash: str | None = None,
        file_size: int | None = None,
        filename: str | None = None,
        search_tags: str | None = None,
        season: int | None = None,
        episode: int | None = None,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """
        Search for subtitles.

        Args:
            imdb_id: IMDB ID of the media
            video_hash: OpenSubtitles hash of the video file
            file_size: Size of the video file in bytes
            filename: Original filename (for fallback matching)
            search_tags: Comma-separated tags (release group, format) for OpenSubtitles
            season: Season number (for TV shows)
            episode: Episode number (for TV shows)
            language: ISO 639-3 language code

        Returns:
            list of subtitle results
        """
        pass

    @abstractmethod
    def download_subtitle(self, subtitle_info: dict[str, Any]) -> str | None:
        """Download subtitle content."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass
