"""
Naming service for generating clean VFS paths from original filenames.

This is the single source of truth for path generation in RivenVFS.
Supports flexible naming templates configured in settings.
"""

import os
from re import Match
from typing import Any, Generic, TypeVar, cast
from loguru import logger
from pydantic import BaseModel, computed_field

from program.media.item import MediaItem, Movie, Show, Season, Episode
from program.settings import settings_manager
from PTT import parse_title  # pyright: ignore[reportUnknownVariableType]

from program.media.media_entry import MediaEntry
from program.utils.safe_formatter import SafeFormatter


T = TypeVar("T", bound=MediaItem)


class NameBuilder(BaseModel, Generic[T]):
    """
    Context data for naming templates.

    Holds all relevant metadata for rendering naming templates.
    """

    class ShowData(BaseModel):
        title: str
        year: int | None
        tvdb_id: str | None
        imdb_id: str | None

    def __init__(self, item: T):
        self._item = item

        if (
            self._item.filesystem_entry
            and isinstance(self._item.filesystem_entry, MediaEntry)
            and self._item.filesystem_entry.media_metadata
        ):
            self._metadata = self._item.filesystem_entry.media_metadata
        else:
            self._metadata = None

    @computed_field
    @property
    def title(self) -> str:
        """Get title from item"""

        assert self._item.title is not None

        return self._item.title

    @computed_field
    @property
    def season(self) -> int | None:
        """Get season number if applicable"""

        if isinstance(self._item, Season):
            return self._item.number or 1

        if isinstance(self._item, Episode):
            return self._item.parent.number or 1

        return None

    @computed_field
    @property
    def episode(self) -> int | None:
        """Get episode number if applicable"""

        if isinstance(self._item, Episode):
            assert self._item.number is not None
            return self._item.number

        return None

    @computed_field
    @property
    def show(self) -> ShowData | None:
        """Get show-level data if applicable"""

        if isinstance(self._item, Episode):
            top_parent = self._item.get_top_parent()

            return self.ShowData.model_validate(
                {
                    "title": top_parent.title,
                    "year": top_parent.year,
                    "tvdb_id": top_parent.tvdb_id,
                    "imdb_id": top_parent.imdb_id,
                }
            )

        return None

    @computed_field
    @property
    def type(self) -> str:
        """Get type of item (movie, show, season, episode)"""

        return self._item.type

    @computed_field
    @property
    def year(self) -> int | None:
        """Get year from item if applicable"""

        return self._item.year

    @computed_field
    @property
    def imdb_id(self) -> str | None:
        """Get IMDb ID from item if applicable"""

        return self._item.imdb_id

    @computed_field
    @property
    def tmdb_id(self) -> str | None:
        """Get TMDB ID from item if applicable"""

        return self._item.tmdb_id

    @computed_field
    @property
    def tvdb_id(self) -> str | None:
        """Get TVDB ID from item if applicable"""

        return self._item.tvdb_id

    @computed_field
    @property
    def resolution(self) -> str | None:
        """Get resolution label from media metadata (e.g., "1080p", "4K")"""

        if not self._metadata or not self._metadata.video:
            return None

        return self._metadata.video.resolution_label

    @computed_field
    @property
    def codec(self) -> str | None:
        """Get video codec from media metadata (e.g., "H.264", "HEVC")"""

        if not self._metadata or not self._metadata.video:
            return None

        return self._metadata.video.codec

    @computed_field
    @property
    def audio(self) -> str | None:
        """Get primary audio codec from media metadata (e.g., "DTS", "AAC")"""

        if not self._metadata or not self._metadata.audio_tracks:
            return None

        return self._metadata.audio_tracks[0].codec

    @computed_field
    @property
    def hdr(self) -> list[str] | None:
        """Get HDR types from media metadata (e.g., ["HDR10", "Dolby Vision"])"""

        if (
            not self._metadata
            or not self._metadata.video
            or not self._metadata.video.hdr_type
        ):
            return None

        return [self._metadata.video.hdr_type]

    @computed_field
    @property
    def quality(self) -> str | None:
        """Get quality source from media metadata (e.g., "BluRay", "WEB-DL")"""

        if not self._metadata:
            return None

        return self._metadata.quality_source

    @computed_field
    @property
    def container(self) -> str | None:
        """Get container format from media metadata (e.g., "matroska", "mp4")"""

        if not self._metadata or not self._metadata.container_formats:
            return None

        return self._metadata.container_formats[0]

    @computed_field
    @property
    def is_remux(self) -> str | None:
        """String flag for remux status ("REMUX" or "")"""

        if not self._metadata:
            return None

        return "REMUX" if self._metadata.is_remux else None

    @computed_field
    @property
    def is_proper(self) -> str | None:
        """String flag for proper status ("PROPER" or "")"""

        if not self._metadata:
            return None

        return "PROPER" if self._metadata.is_proper else None

    @computed_field
    @property
    def repack(self) -> str | None:
        """String flag for repack status ("REPACK" or "")"""

        if not self._metadata:
            return None

        return "REPACK" if self._metadata.is_repack else None

    @computed_field
    @property
    def extended(self) -> str | None:
        """String flag for extended status ("Extended" or "")"""

        if not self._metadata:
            return None

        return "Extended" if self._metadata.is_extended else None

    @computed_field
    @property
    def directors_cut(self) -> str | None:
        """String flag for director's cut status ("Director's Cut" or "")"""

        if not self._metadata:
            return None

        return "Director's Cut" if self._metadata.is_directors_cut else None

    @computed_field
    @property
    def edition(self) -> str | None:
        """Combined edition string (e.g., "Extended Director's Cut")"""

        if not self._metadata:
            return None

        edition_parts = set[str]()

        if self._metadata.is_extended:
            edition_parts.add("Extended")

        if self._metadata.is_directors_cut:
            edition_parts.add("Director's Cut")

        return " ".join(edition_parts)

    def to_format(self, format: str) -> str:
        """Format the NameBuilder using a custom format string"""

        return SafeFormatter().format(format, **self.model_dump())


class NamingService:
    """
    Service for generating clean VFS paths from original filenames and metadata.

    This replaces the old path_utils.generate_target_path() and centralizes
    all path generation logic in RivenVFS.

    Uses configurable naming templates from settings.filesystem for flexible
    file and directory naming.
    """

    def __init__(self):
        self.key = "naming_service"
        self.formatter = SafeFormatter()

    def generate_clean_path(
        self,
        item: MediaItem,
        original_filename: str,
    ) -> str:
        """
        Generate clean VFS path from original filename and item metadata.

        This is the SINGLE source of truth for path generation.

        Args:
            item: MediaItem with metadata (title, year, type, etc.)
            original_filename: Original filename from debrid provider
            file_size: File size in bytes (for validation)
            media_metadata: Optional cached media metadata to avoid re-parsing

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

        # Get extension from original filename
        extension = os.path.splitext(original_filename)[1][1:] or "mkv"

        # Determine base path (/movies or /shows)
        base_path = self._determine_base_path(item)

        # Generate folder structure
        folder_path = self._create_folder_structure(item, base_path)

        # Generate clean filename
        filename = self._generate_clean_filename(item)

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

        if isinstance(item, (Show, Season, Episode)):
            return "/shows"

        return "/movies"

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
            raise ValueError(f"Unknown item type: {type(item)}")

    def _create_movie_folder(self, item: Movie, base_path: str) -> str:
        """
        Create folder structure for movie using template from settings.

        Template: settings.filesystem.movie_dir_template
        Default: "{title} ({year}) {{tmdb-{tmdb_id}}}"
        """

        # Build context for template
        context = NameBuilder(item=item)

        # Get template from settings
        template = settings_manager.settings.filesystem.movie_dir_template

        # Render template
        try:
            segment = context.to_format(template)
            segment = self._sanitize_name(segment)
        except Exception as e:
            logger.warning(
                f"Failed to render movie_dir_template: {e}, falling back to title"
            )
            segment = self._sanitize_name(context.title)

        return f"{base_path}/{segment}" if segment else base_path

    def _create_show_folder(self, item: Show | Season | Episode, base_path: str) -> str:
        """
        Create folder structure for show/season/episode using templates from settings.

        Templates:
        - Show dir: settings.filesystem.show_dir_template
        - Season dir: settings.filesystem.season_dir_template
        """

        # Build show directory context
        show_context = NameBuilder(item=item.get_top_parent())

        # Render show directory template
        show_dir_template = settings_manager.settings.filesystem.show_dir_template

        try:
            segment = show_context.to_format(show_dir_template)
            segment = self._sanitize_name(segment)
        except Exception as e:
            logger.warning(
                f"Failed to render show_dir_template: {e}, falling back to title"
            )
            segment = self._sanitize_name(show_context.title)

        folder = f"{base_path}/{segment}" if segment else base_path

        # Add season folder for seasons/episodes
        if isinstance(item, (Season, Episode)):
            # Derive season number from the Season itself or parent of Episode
            if isinstance(item, Season):
                season_context = NameBuilder(item=item)
            else:
                season_context = NameBuilder(item=item.parent)

            # Render season directory template
            season_template = settings_manager.settings.filesystem.season_dir_template

            try:
                season_segment = self._sanitize_name(
                    season_context.to_format(season_template)
                )
            except Exception as e:
                logger.warning(
                    f"Failed to render season_dir_template: {e}, falling back to default"
                )
                season_segment = f"Season {str(season_context.season).zfill(2)}"

            folder += f"/{season_segment}"

        return folder

    def _generate_clean_filename(self, item: MediaItem) -> str:
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
            return self._generate_episode_filename(item)
        else:
            # Fallback
            return self._sanitize_name(item.title or "Unknown")

    def _generate_movie_filename(self, item: Movie) -> str:
        """
        Generate clean filename for movie using template from settings.

        Template: settings.filesystem.movie_file_template
        Default: "{title} ({year})"

        Includes media metadata from MediaEntry if available.
        """

        # Build base context
        context = NameBuilder(item=item)

        # Get template from settings
        template = settings_manager.settings.filesystem.movie_file_template

        # Render template
        try:
            return self._sanitize_name(context.to_format(template))
        except Exception as e:
            logger.warning(
                f"Failed to render movie_file_template: {e}, falling back to title"
            )
            return self._sanitize_name(context.title)

    def _generate_episode_filename(self, item: Episode) -> str:
        """
        Generate clean filename for episode using template from settings.

        Template: settings.filesystem.episode_file_template
        Default: "{show[title]} - s{season:02d}e{episode:02d}"

        For multi-episode files, automatically formats episode numbers as EXX-YY
        (or EX-Y) based on the episode number formatting in the template.

        Includes media metadata from MediaEntry if available.
        """

        # Build context for template
        episode_context = NameBuilder(item=item)

        # Use show-level (top parent) for title/year
        season_context = NameBuilder(item=item.get_top_parent())

        # Check for multi-episode file from metadata
        # Default to single episode
        episodes = list[int](
            [episode_context.episode] if episode_context.episode is not None else []
        )

        parsed: dict[str, Any] | None = None

        if (
            isinstance(item.filesystem_entry, MediaEntry)
            and not item.filesystem_entry.media_metadata
        ):
            original_filename = item.filesystem_entry.original_filename

            try:
                parsed = cast(dict[str, Any], parse_title(original_filename))

                if parsed.get("episodes") and len(parsed["episodes"]) > 1:
                    episodes = list[int](sorted(parsed["episodes"]))
            except Exception as e:
                logger.warning(f"Failed to parse filename '{original_filename}': {e}")
                parsed = None

        # Get template from settings
        template = settings_manager.settings.filesystem.episode_file_template

        # For multi-episode files, modify the template to use range format
        if len(episodes) > 1:
            template = self._adapt_template_for_multi_episode(template, episodes)

        # Render template
        try:
            return self._sanitize_name(episode_context.to_format(template))
        except Exception as e:
            logger.warning(
                f"Failed to render episode_file_template: {e}, falling back to default"
            )

            # Fallback to default format
            if len(episodes) > 1:
                episode_string = f"e{episodes[0]:02d}-{episodes[-1]:02d}"
            else:
                episode_string = f"e{item.number:02d}"

            return self._sanitize_name(
                f"{season_context.title} - s{episode_context.season:02d}{episode_string}"
            )

    def _adapt_template_for_multi_episode(
        self,
        template: str,
        episodes: list[int],
    ) -> str:
        """
        Adapt episode template for multi-episode files.

        Automatically converts {episode} or {episode:02d} to EXX-YY format
        based on the formatting specified in the template.

        Args:
            template: Original episode template
            episodes: List of episode numbers (sorted)

        Returns:
            Modified template with multi-episode formatting

        Examples:
            "{show[title]} - s{season:02d}e{episode:02d}" -> "{show[title]} - s{season:02d}e01-05"
            "S{season}E{episode}" -> "S{season}E1-5"
        """
        import re

        # Find {episode} or {episode:format} in the template
        # Match patterns like {episode}, {episode:02d}, {episode:d}, etc.
        pattern = r"\{episode(?::([^}]+))?\}"

        def replace_episode(match: Match[str]):
            format_spec = match.group(1) or ""  # Get format spec (e.g., "02d")
            first_ep = episodes[0]
            last_ep = episodes[-1]

            # Format both episode numbers using the same format spec
            if format_spec:
                first_str = f"{first_ep:{format_spec}}"
                last_str = f"{last_ep:{format_spec}}"
            else:
                first_str = str(first_ep)
                last_str = str(last_ep)

            # Return the range format (e.g., "01-05" or "1-5")
            return first_str + "-" + last_str

        # Replace all {episode} occurrences with the range format
        adapted = re.sub(pattern, replace_episode, template)

        return adapted

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

        # Remove empty brackets/parens/braces
        _cleanup_chars = ["[ ]", "[]", "( )", "()", "{ }", "{}"]
        if any(x in name for x in _cleanup_chars):
            for x in _cleanup_chars:
                name = name.replace(x, "")

        # Close gaps around brackets/parens/braces
        _cleanup_chars = ["[ ", " ]", "( ", " )", "{ ", " }"]
        if any(x in name for x in _cleanup_chars):
            for x in _cleanup_chars:
                name = name.replace(x, x.strip())

        # Trim whitespace
        name = name.strip()

        return name


# Global instance for easy access
naming_service = NamingService()


def generate_clean_path(
    item: MediaItem,
    original_filename: str,
) -> str:
    """
    Convenience function for generating clean VFS paths.

    This is the main entry point for path generation.
    """

    return naming_service.generate_clean_path(
        item=item,
        original_filename=original_filename,
    )
