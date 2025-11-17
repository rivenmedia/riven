"""Base indexer module"""

from loguru import logger

from program.media.item import MediaItem, Movie, Show
from program.settings.manager import settings_manager
from program.core.runner import Runner
from program.settings.models import IndexerModel


class BaseIndexer(Runner[IndexerModel]):
    """Base class for all indexers"""

    def __init__(self) -> None:
        super().__init__()

        self.settings = settings_manager.settings.indexer
        self.initialized = True

    @staticmethod
    def copy_attributes(source: MediaItem, target: MediaItem) -> None:
        """Copy attributes from source to target."""

        attributes = [
            "file",
            "folder",
            "update_folder",
            "symlinked",
            "is_anime",
            "symlink_path",
            "subtitles",
            "requested_by",
            "requested_at",
            "overseerr_id",
            "active_stream",
            "requested_id",
            "streams",
        ]

        for attr in attributes:
            target.set(attr, getattr(source, attr, None))

    def copy_items[T: MediaItem](self, item_a: MediaItem, item_b: T) -> T:
        """Copy attributes from itema to itemb recursively."""

        is_anime = item_a.is_anime or item_b.is_anime

        if isinstance(item_a, MediaItem) and isinstance(item_b, Show):
            item_a.seasons = item_b.seasons

        if isinstance(item_b, Show) and not isinstance(item_a, Movie):
            for season_a in item_a.seasons:
                for season_b in item_b.seasons:
                    if season_a.number == season_b.number:  # Check if seasons match
                        for episode_a in season_a.episodes:
                            for episode_b in season_b.episodes:
                                if (
                                    episode_a.number == episode_b.number
                                ):  # Check if episodes match
                                    self.copy_attributes(episode_a, episode_b)
                        season_b.set("is_anime", is_anime)
            item_b.set("is_anime", is_anime)
        elif isinstance(item_b, Movie):
            self.copy_attributes(item_a, item_b)
            item_b.set("is_anime", is_anime)
        else:
            logger.error(
                f"Item types {item_a.type} and {item_b.type} do not match cant copy metadata"
            )

        return item_b
