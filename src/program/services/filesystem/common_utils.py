"""
Common utilities used by FilesystemService (VFS-only).
"""

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States


def get_items_to_update(item: MediaItem) -> list[MediaItem]:
    """
    Return leaf items to process (movies/episodes), expanding shows/seasons.

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
            return [ep for ep in item.episodes if ep.state == States.Downloaded]
    except Exception:
        pass

    return []
