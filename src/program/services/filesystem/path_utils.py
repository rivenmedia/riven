"""
Shared path generation utilities for filesystem operations in VFS-only mode.
Used by Downloader to generate target paths for items.
"""

import os
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.downloaders.models import ParsedFileData


def _determine_target_filename(item: MediaItem, file_data: ParsedFileData) -> str:
    """Determine the target filename using item attributes and optional parsed file data

    Args:
        item: The MediaItem to generate filename for
        file_data: Optional pre-parsed file data for multi-episode detection
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
    """Determine the base path (movies, shows, anime_movies, anime_shows)"""
    # Check by type attribute first (for compatibility with mock objects)
    item_type = getattr(item, 'type', None)

    if item_type == 'movie' or isinstance(item, Movie):
        return "/anime_movies" if (settings.separate_anime_dirs and is_anime) else "/movies"
    elif item_type in ['show', 'season', 'episode'] or isinstance(item, (Show, Season, Episode)):
        return "/anime_shows" if (settings.separate_anime_dirs and is_anime) else "/shows"
    else:
        return "/movies"  # Fallback


def create_folder_structure(item: MediaItem, base_path: str) -> str:
    """Create the folder structure path"""
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


def generate_target_path(item: MediaItem, settings, original_filename: str = None, file_data: ParsedFileData = None) -> str:
    """Generate a complete target path for an item

    Args:
        item: The MediaItem to generate path for
        settings: Filesystem settings
        original_filename: Optional original filename to extract extension from
        file_data: Optional pre-parsed file data for multi-episode detection (avoids re-parsing)
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
        return f"/movies/{item.title}.{extension}"

    vfs_filename = f"{filename}.{extension}"

    # Generate folder structure using shared logic
    base_path = determine_base_path(item, settings, is_anime)
    folder_path = create_folder_structure(item, base_path)

    # Combine folder path and filename, ensuring proper path separators
    full_path = f"{folder_path}/{vfs_filename.replace('/', '-')}"

    return full_path
