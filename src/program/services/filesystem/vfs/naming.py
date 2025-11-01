"""
Naming service for generating clean VFS paths from original filenames.

This is the single source of truth for path generation in RivenVFS.
Supports flexible naming templates configured in settings.
"""

import os
from string import Formatter
from typing import Optional
from loguru import logger

from program.media.item import MediaItem, Movie, Show, Season, Episode
from program.media.models import VideoMetadata
from program.settings.manager import settings_manager
from PTT import parse_title


class SafeFormatter(Formatter):
    """
    Custom string formatter that handles missing keys gracefully.

    Supports:
    - Simple variables: {title}
    - Nested access: {show[title]}
    - List indexing: {episodes[0]}, {episodes[-1]}
    - Format specs: {season:02d}
    - Missing values render as empty string (no KeyError)
    """

    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            # Handle nested access: show[title]
            if "[" in key and "]" in key:
                parts = key.replace("]", "").split("[")
                value = kwargs.get(parts[0], {})
                for part in parts[1:]:
                    if isinstance(value, dict):
                        value = value.get(part, "")
                    elif isinstance(value, list):
                        try:
                            # Handle negative indices like [-1]
                            value = value[int(part)]
                        except (ValueError, IndexError):
                            value = ""
                    else:
                        value = ""
                return value or ""
            # Simple key access
            return kwargs.get(key, "")
        return super().get_value(key, args, kwargs)

    def format_field(self, value, format_spec):
        if value is None or value == "":
            return ""
        return super().format_field(value, format_spec)


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
        file_size: int = 0,
        media_metadata: Optional[dict] = None,
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
        # Use cached media metadata if available, otherwise parse the filename
        if media_metadata:
            parsed = media_metadata
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
        Create folder structure for movie using template from settings.

        Template: settings.filesystem.movie_dir_template
        Default: "{title} ({year}) {{tmdb-{tmdb_id}}}"
        """
        # Build context for template
        context = {
            "title": getattr(item, "title", None) or "",
            "year": getattr(item, "year", None),
            "tmdb_id": getattr(item, "tmdb_id", None),
            "imdb_id": getattr(item, "imdb_id", None),
            "type": "movie",
        }

        # Get template from settings
        template = settings_manager.settings.filesystem.movie_dir_template

        # Render template
        try:
            segment = self.formatter.format(template, **context)
            segment = self._sanitize_name(segment)
        except Exception as e:
            logger.warning(
                f"Failed to render movie_dir_template: {e}, falling back to title"
            )
            segment = self._sanitize_name(context["title"])

        return f"{base_path}/{segment}" if segment else base_path

    def _create_show_folder(self, item: Show | Season | Episode, base_path: str) -> str:
        """
        Create folder structure for show/season/episode using templates from settings.

        Templates:
        - Show dir: settings.filesystem.show_dir_template
        - Season dir: settings.filesystem.season_dir_template
        """
        # Determine the top-most parent (Show-level for seasons/episodes)
        top_parent = self._get_top_parent(item)

        # Extract show-level metadata
        title_str = self._extract_title(top_parent) or self._extract_title(item) or ""

        # Year: from top parent aired_at or year
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
        imdb_id = getattr(top_parent, "imdb_id", None)

        # Build show directory context
        show_context = {
            "title": title_str,
            "year": year,
            "tvdb_id": tvdb_id,
            "imdb_id": imdb_id,
            "type": "show",
        }

        # Render show directory template
        show_template = settings_manager.settings.filesystem.show_dir_template
        try:
            segment = self.formatter.format(show_template, **show_context)
            segment = self._sanitize_name(segment)
        except Exception as e:
            logger.warning(
                f"Failed to render show_dir_template: {e}, falling back to title"
            )
            segment = self._sanitize_name(title_str)

        folder = f"{base_path}/{segment}" if segment else base_path

        # Add season folder for seasons/episodes
        if isinstance(item, (Season, Episode)):
            # Derive season number from the Season itself or parent of Episode
            if isinstance(item, Season):
                season_num = getattr(item, "number", 1) or 1
            else:  # Episode
                season_num = getattr(getattr(item, "parent", None), "number", 1) or 1

            # Build season directory context
            season_context = {
                "season": season_num,
                "show": show_context,  # Nested show data
                "type": "season",
            }

            # Render season directory template
            season_template = settings_manager.settings.filesystem.season_dir_template
            try:
                season_segment = self.formatter.format(
                    season_template, **season_context
                )
                season_segment = self._sanitize_name(season_segment)
            except Exception as e:
                logger.warning(
                    f"Failed to render season_dir_template: {e}, falling back to default"
                )
                season_segment = f"Season {str(season_num).zfill(2)}"

            folder += f"/{season_segment}"

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
        Generate clean filename for movie using template from settings.

        Template: settings.filesystem.movie_file_template
        Default: "{title} ({year})"

        Includes media metadata from MediaEntry if available.
        """
        # Build base context
        context = {
            "title": getattr(item, "title", None) or "",
            "year": getattr(item, "year", None),
            "tmdb_id": getattr(item, "tmdb_id", None),
            "imdb_id": getattr(item, "imdb_id", None),
            "type": "movie",
        }

        # Add media metadata from MediaEntry if available
        context.update(self._extract_media_metadata(item))

        # Get template from settings
        template = settings_manager.settings.filesystem.movie_file_template

        # Render template
        try:
            filename = self.formatter.format(template, **context)
            return self._sanitize_name(filename)
        except Exception as e:
            logger.warning(
                f"Failed to render movie_file_template: {e}, falling back to title"
            )
            return self._sanitize_name(context["title"])

    def _generate_episode_filename(
        self, item: Episode, parsed: Optional[dict] = None
    ) -> str:
        """
        Generate clean filename for episode using template from settings.

        Template: settings.filesystem.episode_file_template
        Default: "{show[title]} - s{season:02d}e{episode:02d}"

        Includes media metadata from MediaEntry if available.
        """
        # Use show-level (top parent) for title/year
        top_parent = self._get_top_parent(item)
        title_str = self._extract_title(top_parent) or self._extract_title(item) or ""

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

        # Check for multi-episode file from metadata
        episodes = [episode_num]  # Default to single episode
        if parsed:
            # MediaMetadata has 'episodes' as a list
            if isinstance(parsed, dict):
                parsed_episodes = parsed.get("episodes")
                if parsed_episodes and len(parsed_episodes) > 1:
                    episodes = sorted(parsed_episodes)
            elif hasattr(parsed, "episodes"):
                parsed_episodes = getattr(parsed, "episodes")
                if parsed_episodes and len(parsed_episodes) > 1:
                    episodes = sorted(parsed_episodes)

        # Build context for template
        context = {
            "title": getattr(item, "title", None) or "",
            "season": season_num,
            "episode": episode_num,
            "episodes": episodes,  # List for multi-episode files
            "show": {  # Nested show data
                "title": title_str,
                "year": year,
                "tvdb_id": getattr(top_parent, "tvdb_id", None),
                "imdb_id": getattr(top_parent, "imdb_id", None),
            },
            "type": "episode",
        }

        # Add media metadata from MediaEntry if available
        context.update(self._extract_media_metadata(item))

        # Get template from settings
        template = settings_manager.settings.filesystem.episode_file_template

        # Render template
        try:
            filename = self.formatter.format(template, **context)
            return self._sanitize_name(filename)
        except Exception as e:
            logger.warning(
                f"Failed to render episode_file_template: {e}, falling back to default"
            )
            # Fallback to default format
            if len(episodes) > 1:
                episode_string = f"e{str(episodes[0]):02d}-e{str(episodes[-1]):02d}"
            else:
                episode_string = f"e{episode_num:02d}"
            return self._sanitize_name(
                f"{title_str} - s{season_num:02d}{episode_string}"
            )

    def _extract_media_metadata(self, item: MediaItem) -> dict:
        """
        Extract media metadata from MediaEntry for use in templates.

        Returns dict with keys: resolution, codec, hdr, audio, quality, container,
        is_remux, is_proper, is_repack, is_extended, is_directors_cut,
        plus string versions: remux, proper, repack, extended, directors_cut, edition
        """
        metadata = {}

        # Get MediaEntry from item
        media_entry = None
        if hasattr(item, "filesystem_entries") and item.filesystem_entries:
            # Get first MediaEntry (there should only be one for movies/episodes)
            media_entry = item.filesystem_entries[0]

        if not media_entry or not hasattr(media_entry, "media_metadata"):
            return metadata

        media_metadata = getattr(media_entry, "media_metadata", None)
        if not media_metadata:
            return metadata

        # Extract video metadata
        video = media_metadata.get("video", {})
        if video:
            # Get resolution using VideoMetadata.resolution_label property
            # This handles ultrawide content correctly (e.g., 3840×1600 → "4K")
            resolution = video.get("resolution")
            if not resolution:
                # Instantiate VideoMetadata to use its resolution_label property
                try:
                    video_obj = VideoMetadata(**video)
                    resolution = video_obj.resolution_label
                except Exception:
                    # Fallback if VideoMetadata instantiation fails
                    resolution = None
            metadata["resolution"] = resolution
            metadata["codec"] = video.get("codec")

            # HDR - handle both hdr_type (single string) and hdr (list)
            hdr = video.get("hdr", [])
            if not hdr and video.get("hdr_type"):
                hdr = [video.get("hdr_type")]
            metadata["hdr"] = hdr

        # Extract audio metadata (first track)
        audio_tracks = media_metadata.get("audio_tracks", [])
        if audio_tracks:
            metadata["audio"] = audio_tracks[0].get("codec")

        # Extract quality/release metadata
        metadata["quality"] = media_metadata.get("quality_source")

        # Container - get first format from list (e.g., "matroska" from ["matroska", "webm"])
        container_formats = media_metadata.get("container_format", [])
        metadata["container"] = container_formats[0] if container_formats else None

        # Boolean flags
        is_remux = media_metadata.get("is_remux", False)
        is_proper = media_metadata.get("is_proper", False)
        is_repack = media_metadata.get("is_repack", False)
        is_extended = media_metadata.get("is_extended", False)
        is_directors_cut = media_metadata.get("is_directors_cut", False)

        metadata["is_remux"] = is_remux
        metadata["is_proper"] = is_proper
        metadata["is_repack"] = is_repack
        metadata["is_extended"] = is_extended
        metadata["is_directors_cut"] = is_directors_cut

        # String versions for easier template use (empty string if False)
        metadata["remux"] = "REMUX" if is_remux else ""
        metadata["proper"] = "PROPER" if is_proper else ""
        metadata["repack"] = "REPACK" if is_repack else ""
        metadata["extended"] = "Extended" if is_extended else ""
        metadata["directors_cut"] = "Director's Cut" if is_directors_cut else ""

        # Combined edition string (for convenience)
        edition_parts = []
        if is_extended:
            edition_parts.append("Extended")
        if is_directors_cut:
            edition_parts.append("Director's Cut")
        metadata["edition"] = " ".join(edition_parts)

        return metadata

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
    media_metadata: Optional[dict] = None,
) -> str:
    """
    Convenience function for generating clean VFS paths.

    This is the main entry point for path generation.
    """
    return naming_service.generate_clean_path(
        item, original_filename, file_size, media_metadata
    )
