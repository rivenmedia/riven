"""
Common utilities used by FilesystemService (VFS-only).

This module provides helper functions for the FilesystemService:
- get_items_to_update: Filter items to only leaf items (movies/episodes)

Note: In the current architecture, only Movies and Episodes reach FilesystemService.
Shows and Seasons never reach Downloaded state and are handled differently.
"""
from typing import List

from program.media.item import Episode, MediaItem, Movie
from program.media.state import States


def get_items_to_update(item: MediaItem) -> List[MediaItem]:
    """
    Return leaf items to process (movies/episodes).

    Filters out Shows and Seasons since they never reach FilesystemService
    in the current architecture. Only Movies and Episodes have actual files
    that need to be registered in the VFS.

    Args:
        item: The MediaItem to filter.

    Returns:
        List[MediaItem]: List containing the item if it's a Movie or Episode,
                        empty list otherwise.

    Note: Shows/Seasons never reach Downloaded state in the new architecture.
    """
    try:
        if isinstance(item, (Movie, Episode)):
            return [item]
        # Shows/Seasons should never reach here, but handle gracefully
        return []
    except Exception:
        ...
    return []
