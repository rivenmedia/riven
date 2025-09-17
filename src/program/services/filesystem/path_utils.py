"""
Shared path generation utilities for filesystem operations in VFS-only mode.
Used by FilesystemService to ensure consistent naming.
"""

import os
from typing import Union
from program.media.item import Episode, MediaItem, Movie, Season, Show


def determine_target_filename(item: MediaItem) -> str:
    """Determine the target filename using consistent logic across filesystem implementations"""  
    if isinstance(item, Movie):
        return f"{item.title} ({item.aired_at.year}) " + "{tmdb-" + item.tmdb_id + "}"
    elif isinstance(item, Season):
        showname = item.parent.title
        showyear = item.parent.aired_at.year
        return f"{showname} ({showyear}) - Season {str(item.number).zfill(2)}"
    elif isinstance(item, Episode):
        episodes_from_file = item.get_file_episodes()
        if len(episodes_from_file) > 1:
            first_episode_number = item.number
            last_episode_number = first_episode_number + len(episodes_from_file) - 1
            episode_string = f"e{str(first_episode_number).zfill(2)}-e{str(last_episode_number).zfill(2)}"
        else:
            episode_string = f"e{str(item.number).zfill(2)}"

        if episode_string:
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


def generate_target_path(item: MediaItem, settings) -> str:
    """Generate a complete target path for an item"""
    # Determine if this is anime content
    is_anime = hasattr(item, "is_anime") and item.is_anime
    
    # Get the original filename and extension from FilesystemEntry
    if item.filesystem_entry and item.filesystem_entry.original_filename:
        original_filename = item.filesystem_entry.original_filename
        extension = os.path.splitext(original_filename)[1][1:]  # Remove the dot
    else:
        # Default extension if no filesystem entry
        extension = "mkv"
    
    # Generate filename using shared logic
    filename = determine_target_filename(item)
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
