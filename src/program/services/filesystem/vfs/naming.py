"""
Naming service for generating clean VFS paths from original filenames.

This is the single source of truth for path generation in RivenVFS.
Supports flexible naming templates for future customization.
"""

import os
from typing import Optional
from loguru import logger

from program.media.item import MediaItem, Movie, Show, Season, Episode
from PTT import parse_title


class NamingService:
    """
    Service for generating clean VFS paths from original filenames and metadata.

    This replaces the old path_utils.generate_target_path() and centralizes
    all path generation logic in RivenVFS.
    """

    def __init__(self):
        self.key = "naming_service"

    def generate_clean_path(
        self,
        item: MediaItem,
        original_filename: str,
        file_size: int = 0,
        parsed_data: Optional[dict] = None,
    ) -> str:
        """
        Generate clean VFS path from original filename and item metadata.

        This is the SINGLE source of truth for path generation.

        Args:
            item: MediaItem with metadata (title, year, type, etc.)
            original_filename: Original filename from debrid provider
            file_size: File size in bytes (for validation)
            parsed_data: Optional cached parsed data from RTN to avoid re-parsing

        Returns:
            Clean VFS path (e.g., "/movies/Movie (2024)/Movie.mkv")

        Example:
            >>> naming = NamingService()
            >>> naming.generate_clean_path(
            ...     movie_item,
            ...     "Movie.2024.1080p.BluRay.x264-GROUP.mkv"
            ... )
            "/movies/Movie (2024) {tmdb-12345}/Movie (2024).mkv"
        """
        # Use cached parsed data if available, otherwise parse the filename
        if parsed_data:
            parsed = parsed_data
        else:
            try:
                parsed = parse_title(original_filename)
            except Exception as e:
                logger.warning(f"Failed to parse filename '{original_filename}': {e}")
                parsed = None

        # Get extension from original filename
        extension = os.path.splitext(original_filename)[1][1:] or "mkv"

        # Determine base path (/movies or /shows)
        base_path = self._determine_base_path(item)

        # Generate folder structure
        folder_path = self._create_folder_structure(item, base_path)

        # Generate clean filename
        filename = self._generate_clean_filename(item, parsed)

        # Combine into full path
        full_path = f"{folder_path}/{filename}.{extension}"

        # Normalize any accidental duplicate slashes without altering directory structure
        full_path = full_path.replace("//", "/")

        return full_path

    def _determine_base_path(self, item: MediaItem) -> str:
        """
        Determine the base path (/movies or /shows) based on item type.

        Args:
            item: MediaItem to determine base path for

        Returns:
            Base path string ("/movies" or "/shows")
        """
        # Check by type attribute first (for compatibility with mock objects)
        item_type = getattr(item, "type", None)

        if item_type == "movie" or isinstance(item, Movie):
            return "/movies"
        elif item_type in ["show", "season", "episode"] or isinstance(
            item, (Show, Season, Episode)
        ):
            return "/shows"
        else:
            return "/movies"  # Fallback

    def _extract_title(self, obj) -> str | None:
        """Safely extract a title string from a MediaItem/Show-like object or string.
        - If obj is a plain string, return it.
        - If obj has a string attribute 'title', return it.
        - Otherwise return None.
        """
        if obj is None:
            return None
        if isinstance(obj, str):
            return obj
        try:
            t = getattr(obj, "title", None)
            return t if isinstance(t, str) else None
        except Exception:
            return None

    def _get_top_parent(self, item: MediaItem):
        """Walk up the parent chain to the top-most parent object.
        Returns the item itself if no parent is present.
        """
        current = item
        seen = 0
        try:
            while (
                hasattr(current, "parent")
                and getattr(current, "parent") is not None
                and seen < 10
            ):
                current = getattr(current, "parent")
                seen += 1
        except Exception:
            # If anything unexpected, just return the last known object
            return current
        return current

    def _create_folder_structure(self, item: MediaItem, base_path: str) -> str:
        """
        Create folder structure for item.

        Args:
            item: MediaItem to create folder for
            base_path: Base path ("/movies" or "/shows")

        Returns:
            Full folder path

        Examples:
            Movie: "/movies/Title (Year) {tmdb-id}"
            Episode: "/shows/Title (Year) {tvdb-id}/Season XX"
        """
        if isinstance(item, Movie):
            return self._create_movie_folder(item, base_path)
        elif isinstance(item, (Show, Season, Episode)):
            return self._create_show_folder(item, base_path)
        else:
            # Fallback to something stable using the item's own title
            safe_title = self._sanitize_name(self._extract_title(item) or "Unknown")
            return f"{base_path}/{safe_title}"

    def _create_movie_folder(self, item: Movie, base_path: str) -> str:
        """
        Create folder structure for movie.

        Default scheme: Title (Year) {tmdb-<tmdb_id>}
        Skips missing parts (no 'Unknown').
        """
        title = self._sanitize_name(getattr(item, "title", None))
        year = getattr(item, "year", None)
        tmdb_id = getattr(item, "tmdb_id", None)

        segment = ""
        if title:
            segment = title
            if year:
                segment += f" ({year})"
            if tmdb_id:
                segment += f" {{tmdb-{tmdb_id}}}"
        elif tmdb_id:
            segment = f"{{tmdb-{tmdb_id}}}"

        return f"{base_path}/{segment}" if segment else base_path

    def _create_show_folder(self, item: Show | Season | Episode, base_path: str) -> str:
        """
        Create folder structure for show/season/episode.

        Format: /shows/Title (Year) {tvdb-id}/Season XX
        """
        # Determine the top-most parent (Show-level for seasons/episodes)
        top_parent = self._get_top_parent(item)

        # Title: prefer top parent title, else item
        title_str = self._extract_title(top_parent) or self._extract_title(item) or ""
        title = self._sanitize_name(title_str)

        # Year: from top parent aired_at or year; avoid 'Unknown'
        year = None
        if hasattr(top_parent, "aired_at") and getattr(top_parent, "aired_at"):
            try:
                year = str(getattr(top_parent, "aired_at")).split("-")[0]
            except (ValueError, IndexError, AttributeError):
                year = None
        if year is None and hasattr(top_parent, "year") and getattr(top_parent, "year"):
            year = getattr(top_parent, "year")
        if year is None and hasattr(item, "year") and getattr(item, "year"):
            year = getattr(item, "year")

        # TVDB ID: strictly from show-level (top parent) when present
        tvdb_id = getattr(top_parent, "tvdb_id", None)

        # Build folder segment without 'Unknown' fallbacks
        segment = title
        if year:
            segment += f" ({year})"
        if tvdb_id:
            segment += f" {{tvdb-{tvdb_id}}}"

        folder = f"{base_path}/{segment}" if segment else base_path

        # Add season folder for seasons/episodes:
        # Folder name must be: "Show (Year) - Season XX" (zero-padded)
        if isinstance(item, (Season, Episode)):
            # Derive season number from the Season itself or parent of Episode
            if isinstance(item, Season):
                season_num = getattr(item, "number", 1) or 1
            else:  # Episode
                season_num = getattr(getattr(item, "parent", None), "number", 1) or 1
            folder += f"/Season {str(season_num).zfill(2)}"
        return folder

    def _generate_clean_filename(
        self, item: MediaItem, parsed: Optional[dict] = None
    ) -> str:
        """
        Generate clean filename from item metadata.

        Args:
            item: MediaItem to generate filename for
            parsed: Optional parsed metadata from PTT

        Returns:
            Clean filename (without extension)

        Examples:
            Movie: "Movie (2024)"
            Episode: "Show - s01e01"
        """
        if isinstance(item, Movie):
            return self._generate_movie_filename(item)
        elif isinstance(item, Episode):
            return self._generate_episode_filename(item, parsed)
        else:
            # Fallback
            return self._sanitize_name(item.title or "Unknown")

    def _generate_movie_filename(self, item: Movie) -> str:
        """
        Generate clean filename for movie.

        Default scheme: "Title (Year) {tmdb-<tmdb_id>}"
        Skips missing parts (no 'Unknown').
        """
        title = self._sanitize_name(getattr(item, "title", None))
        year = getattr(item, "year", None)
        tmdb_id = getattr(item, "tmdb_id", None)

        parts = []
        if title:
            if year:
                parts.append(f"{title} ({year})")
            else:
                parts.append(title)
        if tmdb_id:
            parts.append(f"{{tmdb-{tmdb_id}}}")

        return " ".join(parts) if parts else ""

    def _generate_episode_filename(
        self, item: Episode, parsed: Optional[dict] = None
    ) -> str:
        """
        Generate clean filename for episode.

        Default scheme:
        - Single: "Show (Year) - sYYeXX"
        - Multi: "Show (Year) - sYYeXX-eZZ"
        """
        # Use show-level (top parent) for title/year
        top_parent = self._get_top_parent(item)
        title_str = self._extract_title(top_parent) or self._extract_title(item) or ""
        title = self._sanitize_name(title_str)

        year = None
        if hasattr(top_parent, "aired_at") and getattr(top_parent, "aired_at"):
            try:
                year = str(getattr(top_parent, "aired_at")).split("-")[0]
            except (ValueError, IndexError, AttributeError):
                year = None
        if year is None and getattr(top_parent, "year", None):
            year = getattr(top_parent, "year")

        season_num = item.parent.number if item.parent else 1
        episode_num = item.number

        # Check for multi-episode file from parsed data
        episode_string = f"e{str(episode_num).zfill(2)}"

        episodes = None
        if parsed:
            # RTN's ParsedData has 'episodes' as a list
            if isinstance(parsed, dict):
                episodes = parsed.get("episodes")
            elif hasattr(parsed, "episodes"):
                episodes = getattr(parsed, "episodes")

        if episodes and len(episodes) > 1:
            # Multi-episode file: sYYeXX-eZZ (season & endpoints 2-digit)
            episodes = sorted(episodes)
            episode_string = (
                f"e{str(episodes[0]).zfill(2)}-e{str(episodes[-1]).zfill(2)}"
            )

        prefix = title
        if year:
            prefix += f" ({year})"

        # Filename format: "Show (Year) - sYYeXX" with lowercase s/e
        return f"{prefix} - s{str(season_num).zfill(2)}{episode_string}"

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize name for use in filesystem paths.

        Robustly handles non-string inputs by coercing to string first.

        Removes or replaces characters that are problematic in filenames.

        Args:
            name: Name to sanitize (any type)

        Returns:
            Sanitized name
        """
        # Coerce to string safely
        try:
            if name is None:
                name = ""
            # Avoid accidentally using a built-in method object as the value
            if hasattr(name, "__call__") and not isinstance(name, str):
                # Do not call it; just stringify
                name = str(name)
            else:
                name = str(name)
        except Exception:
            name = ""

        # Replace problematic characters
        replacements = {
            "/": "-",
            "\\": "-",
            ":": " -",
            "*": "",
            "?": "",
            '"': "'",
            "<": "",
            ">": "",
            "|": "-",
        }
        for old, new in replacements.items():
            name = name.replace(old, new)

        # Collapse multiple spaces
        while "  " in name:
            name = name.replace("  ", " ")

        # Trim whitespace
        name = name.strip()

        return name


# Global instance for easy access
naming_service = NamingService()


def generate_clean_path(
    item: MediaItem,
    original_filename: str,
    file_size: int = 0,
    parsed_data: Optional[dict] = None,
) -> str:
    """
    Convenience function for generating clean VFS paths.

    This is the main entry point for path generation.
    """
    return naming_service.generate_clean_path(
        item, original_filename, file_size, parsed_data
    )
