"""
Path generation utilities for RivenVFS.

This module provides utilities for generating virtual filesystem paths:
- _determine_target_filename: Generate filenames for media items
- determine_base_path: Determine base directory (movies/shows/anime)
- create_folder_structure: Build nested folder paths
- generate_target_path: Complete VFS path generation with profile support
- _sanitize_profile_name: Sanitize profile names for filesystem use

Used by Downloader to generate target paths for MediaEntry objects.

Path structure with multi-profile support:
- /{profile_name}/movies/Movie Title (2025) {tmdb-12345}/Movie Title (2025).mkv
- /{profile_name}/shows/Show Title (2024) {tvdb-67890}/Season 01/Show Title S01E01.mkv
"""

import os
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.downloaders.models import ParsedFileData


def _determine_target_filename(item: MediaItem, file_data: ParsedFileData) -> str:
    """
    Builds the target filename for a media item using its attributes and optional parsed file data.
    
    Parameters:
        item (MediaItem): The media item to generate a filename for. Expected types: Movie, Season, or Episode.
        file_data (ParsedFileData): Optional parsed file data used to detect multi-episode files; may be None.
    
    Returns:
        str or None: The generated filename string in one of the following formats:
            - Movie: "Title (Year) {tmdb-<tmdb_id>}"
            - Season: "Show (Year) - Season XX" (season number zero-padded to 2 digits)
            - Episode (single): "Show (Year) - sYYeXX" (season and episode numbers zero-padded to 2 digits)
            - Episode (multi): "Show (Year) - sYYeXX-eZZ" (episode range computed from parsed file data)
        Returns None if the item's type is not handled.
    """
    if isinstance(item, Movie):
        return f"{item.title} ({item.aired_at.year}) " + "{tmdb-" + item.tmdb_id + "}"
    elif isinstance(item, Season):
        showname = item.parent.title
        showyear = item.parent.aired_at.year
        return f"{showname} ({showyear}) - Season {str(item.number).zfill(2)}"
    elif isinstance(item, Episode):
        # Check if this is a multi-episode file using parsed file data
        if file_data and file_data.episodes and len(file_data.episodes) > 1:
            # Multi-episode file
            first_episode_number = item.number
            last_episode_number = first_episode_number + len(file_data.episodes) - 1
            episode_string = f"e{str(first_episode_number).zfill(2)}-e{str(last_episode_number).zfill(2)}"
        else:
            # Single episode
            episode_string = f"e{str(item.number).zfill(2)}"

        showname = item.parent.parent.title
        showyear = item.parent.parent.aired_at.year
        return f"{showname} ({showyear}) - s{str(item.parent.number).zfill(2)}{episode_string}"

    return None


def determine_base_path(item: MediaItem, settings, is_anime: bool = False) -> str:
    """
    Determine the base path for a media item.

    Returns one of:
    - /movies or /anime_movies (for movies)
    - /shows or /anime_shows (for shows/seasons/episodes)

    Args:
        item: MediaItem to determine path for.
        settings: Filesystem settings (for separate_anime_dirs).
        is_anime: Whether the item is anime content.

    Returns:
        str: Base path string (e.g., "/movies", "/anime_shows").
    """
    # Check by type attribute first (for compatibility with mock objects)
    item_type = getattr(item, 'type', None)

    if item_type == 'movie' or isinstance(item, Movie):
        return "/anime_movies" if (settings.separate_anime_dirs and is_anime) else "/movies"
    elif item_type in ['show', 'season', 'episode'] or isinstance(item, (Show, Season, Episode)):
        return "/anime_shows" if (settings.separate_anime_dirs and is_anime) else "/shows"
    else:
        return "/movies"  # Fallback


def create_folder_structure(item: MediaItem, base_path: str) -> str:
    """
    Build the nested folder path for a media item under the given base directory.
    
    Constructs a folder name for Movie as "Title (Year) {tmdb-<tmdb_id>}". For Show, uses "Title (Year) {tvdb-<tvdb_id>}". For Season and Episode, nests a "Season XX" folder (season number zero-padded to two digits) under the show's folder derived from the parent Show. Any forward slashes in titles are replaced with '-' to avoid creating subdirectories. Returns the base_path unchanged for unrecognized item types.
    
    Parameters:
        item: The media item (Movie, Show, Season, or Episode) whose folder structure to build.
        base_path (str): The root directory under which item-specific folders are appended.
    
    Returns:
        str: The full folder path under base_path for the provided item.
    """
    if isinstance(item, Movie):
        movie_folder = f"{item.title.replace('/', '-')} ({item.aired_at.year}) {{tmdb-{item.tmdb_id}}}"
        return f"{base_path}/{movie_folder}"
    elif isinstance(item, Show):
        folder_name_show = f"{item.title.replace('/', '-')} ({item.aired_at.year}) {{tvdb-{item.tvdb_id}}}"
        return f"{base_path}/{folder_name_show}"
    elif isinstance(item, Season):
        show = item.parent
        folder_name_show = f"{show.title.replace('/', '-')} ({show.aired_at.year}) {{tvdb-{show.tvdb_id}}}"
        folder_season_name = f"Season {str(item.number).zfill(2)}"
        return f"{base_path}/{folder_name_show}/{folder_season_name}"
    elif isinstance(item, Episode):
        show = item.parent.parent
        folder_name_show = f"{show.title.replace('/', '-')} ({show.aired_at.year}) {{tvdb-{show.tvdb_id}}}"
        season = item.parent
        folder_season_name = f"Season {str(season.number).zfill(2)}"
        return f"{base_path}/{folder_name_show}/{folder_season_name}"
    else:
        return base_path  # Fallback


def generate_target_path(item: MediaItem, settings, original_filename: str = None, file_data: ParsedFileData = None, profile_name: str = None) -> str:
    """
    Builds the complete VFS target path for a media item, including folder structure and filename.

    With multi-profile support, each scraping profile gets its own root directory in the VFS:
    - /{profile_name}/movies/Movie Title (2025)/Movie Title (2025).mkv
    - /{profile_name}/shows/Show Title (2024)/Season 01/Show Title S01E01.mkv

    Parameters:
        item: The media item to generate a path for (movie, show, season, or episode).
        settings: Filesystem settings that control base directories (e.g., whether anime directories are separated).
        original_filename (str, optional): Source filename to derive the file extension from.
        file_data (ParsedFileData, optional): Pre-parsed file metadata used to detect multi-episode files.
        profile_name (str, optional): Scraping profile name to use as root directory. If None, uses "default".

    Returns:
        str: The full VFS path for the item, including profile root, folders and filename with extension.
    """
    # Determine if this is anime content
    is_anime = hasattr(item, "is_anime") and item.is_anime

    # Get the extension
    if original_filename:
        extension = os.path.splitext(original_filename)[1][1:]  # Remove the dot
    elif item.filesystem_entry and item.filesystem_entry.original_filename:
        extension = os.path.splitext(item.filesystem_entry.original_filename)[1][1:]
    else:
        # Default extension if no filesystem entry
        extension = "mkv"

    # Generate filename using item attributes and optional parsed file data
    filename = _determine_target_filename(item, file_data=file_data)
    if not filename:
        # Fallback
        profile_root = _sanitize_profile_name(profile_name or "default")
        return f"/{profile_root}/movies/{item.title}.{extension}"

    vfs_filename = f"{filename}.{extension}"

    # Generate folder structure using shared logic
    base_path = determine_base_path(item, settings, is_anime)
    folder_path = create_folder_structure(item, base_path)

    # Prepend profile name as root directory
    profile_root = _sanitize_profile_name(profile_name or "default")
    full_path = f"/{profile_root}{folder_path}/{vfs_filename.replace('/', '-')}"

    return full_path


def _sanitize_profile_name(profile_name: str) -> str:
    """
    Sanitize profile name for use in filesystem paths.

    Converts to lowercase, replaces spaces with hyphens, removes special characters.
    Only allows alphanumeric characters, hyphens, and underscores.

    Args:
        profile_name: Profile name to sanitize (e.g., "4K HDR", "1080p").

    Returns:
        str: Sanitized profile name (e.g., "4k-hdr", "1080p").
    """
    import re
    # Convert to lowercase and replace spaces with hyphens
    sanitized = profile_name.lower().replace(" ", "-")
    # Remove any characters that aren't alphanumeric, hyphens, or underscores
    sanitized = re.sub(r'[^a-z0-9\-_]', '', sanitized)
    return sanitized
