"""
Common utilities used by FilesystemService (VFS-only).
"""
from pathlib import Path
from typing import List, Optional

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.settings.manager import settings_manager


def get_items_to_update(item: MediaItem) -> List[MediaItem]:
    """Return leaf items to process (movies/episodes), expanding shows/seasons.
    Only include episodes that have reached Downloaded state for parent inputs.
    """
    try:
        if isinstance(item, (Movie, Episode)):
            return [item]
        if isinstance(item, Show):
            return [
                ep
                for season in item.seasons
                for ep in season.episodes
                if ep.state == States.Downloaded
            ]
        if isinstance(item, Season):
            return [
                ep
                for ep in item.episodes
                if ep.state == States.Downloaded
            ]
    except Exception:
        ...
    return []




def build_abs_library_path(relative_path: str, library_root: Optional[Path] = None) -> Path:
    """Map a relative media path ("/movies/…") to the absolute library path."""
    library = library_root or settings_manager.settings.filesystem.library_path
    return library / relative_path.lstrip("/")

