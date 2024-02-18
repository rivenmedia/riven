"""Mdblist content module"""
from time import time
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get, ping
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt, CLIENT_ID


class Trakt:
    """Content class for Trakt"""

    def __init__(self):
        self.key = "trakt"
        self.api_url = "https://api.trakt.tv"
        self.settings = settings_manager.settings.content.trakt
        self.headers = {"X-Api-Key": self.settings.api_key}
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.updater = Trakt()
        self.next_run_time = 0
        logger.info("Trakt initialized!")

    def validate(self) -> bool:
        """Validate Trakt settings."""
        return NotImplementedError

    def run(self):
        """Fetch media from Trakt and add them to media_items attribute."""
        self.next_run_time = time() + self.settings.update_interval
        watchlist_items = self._get_items_from_trakt_watchlist(self.settings.watchlist)
        collection_items = self._get_items_from_trakt_collections(
            self.settings.collection
        )
        user_list_items = self._get_items_from_trakt_list(self.settings.user_lists)
        items = list(set(watchlist_items + collection_items + user_list_items))
        container = self.updater.create_items(items)
        for item in container:
            item.set("requested_by", "Trakt")
        yield from container

    def _get_items_from_trakt_watchlist(self, watchlist_items: list) -> list:
        """Get items from Trakt watchlist"""
        return NotImplementedError

    def _get_items_from_trakt_collections(self, collection_items: list) -> list:
        """Get items from Trakt collections"""
        return NotImplementedError

    def _get_items_from_trakt_list(self, list_items: list) -> list:
        """Get items from Trakt user list"""
        return NotImplementedError
