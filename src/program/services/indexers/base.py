"""Base indexer module"""

from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.core.runner import Runner
from program.settings.models import IndexerModel


class BaseIndexer(Runner[IndexerModel]):
    """Base class for all indexers"""

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.indexer
        self.initialized = True

    @staticmethod
    def copy_attributes(source, target):
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

    def copy_items(self, itema: MediaItem, itemb: MediaItem):
        """Copy attributes from itema to itemb recursively."""

        is_anime = itema.is_anime or itemb.is_anime

        if itema.type == "mediaitem" and itemb.type == "show":
            itema.seasons = itemb.seasons

        if itemb.type == "show" and itema.type != "movie":
            for seasona in itema.seasons:
                for seasonb in itemb.seasons:
                    if seasona.number == seasonb.number:  # Check if seasons match
                        for episodea in seasona.episodes:
                            for episodeb in seasonb.episodes:
                                if (
                                    episodea.number == episodeb.number
                                ):  # Check if episodes match
                                    self.copy_attributes(episodea, episodeb)
                        seasonb.set("is_anime", is_anime)
            itemb.set("is_anime", is_anime)
        elif itemb.type == "movie":
            self.copy_attributes(itema, itemb)
            itemb.set("is_anime", is_anime)
        else:
            logger.error(
                f"Item types {itema.type} and {itemb.type} do not match cant copy metadata"
            )

        return itemb
