"""Mdblist content module"""
from time import time
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get, ping
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt, CLIENT_ID


class Trakt:
    """Content class for Trakt"""

    def __init__(self, media_items: MediaItemContainer):
        self.key = "trakt"
        self.api_url = "https://api.trakt.tv"
        self.settings = settings_manager.settings.content.trakt
        self.headers = {"X-Api-Key": self.settings.api_key}
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.media_items = media_items
        self.updater = Trakt()
        self.next_run_time = 0
        logger.info("Trakt initialized!")

    def validate(self) -> bool:
        """Validate Trakt settings."""
        return NotImplementedError

    def run(self):
        """Fetch media from Trakt and add them to media_items attribute."""
        if time() < self.next_run_time:
            return
        self.next_run_time = time() + self.settings.update_interval
        watchlist_items = self._get_items_from_trakt_watchlist(self.settings.watchlist)
        collection_items = self._get_items_from_trakt_collections(
            self.settings.collection
        )
        user_list_items = self._get_items_from_trakt_list(self.settings.user_lists)
        items = list(set(watchlist_items + collection_items + user_list_items))
        new_items = [item for item in items if item not in self.media_items]
        container = self.updater.create_items(new_items)
        for item in container:
            item.set("requested_by", "Trakt")
        added_items = self.media_items.extend(container)
        length = len(added_items)
        if length >= 1 and length <= 5:
            for item in added_items:
                logger.info("Added %s", item.log_string)
        elif length > 5:
            logger.info("Added %s items", length)

    def _get_items_from_trakt_watchlist(self, watchlist_items: list) -> list:
        """Get items from Trakt watchlist"""
        return NotImplementedError

    def _get_items_from_trakt_collections(self, collection_items: list) -> list:
        """Get items from Trakt collections"""
        return NotImplementedError

    def _get_items_from_trakt_list(self, list_items: list) -> list:
        """Get items from Trakt user list"""
        return NotImplementedError
