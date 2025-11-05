"""
Base provider interface for subtitle providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class SubtitleProvider(ABC):
    """Abstract base class for subtitle providers."""

    @abstractmethod
    def search_subtitles(
        self,
        imdb_id: str,
        video_hash: Optional[str] = None,
        file_size: Optional[int] = None,
        filename: Optional[str] = None,
        search_tags: Optional[str] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
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
            List of subtitle results
        """

    @abstractmethod
    def download_subtitle(self, subtitle_info: Dict[str, Any]) -> Optional[str]:
        """Download subtitle content."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
