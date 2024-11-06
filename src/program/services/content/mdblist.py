"""Mdblist content module"""

from typing import Generator

from kink import di
from loguru import logger

from program.apis.mdblist_api import MdblistAPI
from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.utils.request import RateLimitExceeded


class Mdblist:
    """Content class for mdblist"""
    def __init__(self):
        self.key = "mdblist"
        self.settings = settings_manager.settings.content.mdblist
        self.api = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.requests_per_2_minutes = self._calculate_request_time()
        logger.success("mdblist initialized")

    def validate(self):
        if not self.settings.enabled:
            return False
        if self.settings.api_key == "" or len(self.settings.api_key) != 25:
            logger.error("Mdblist api key is not set.")
            return False
        if not self.settings.lists:
            logger.error("Mdblist is enabled, but list is empty.")
            return False
        self.api = di[MdblistAPI]
        response = self.api.validate()
        if "Invalid API key!" in response.response.text:
            logger.error("Mdblist api key is invalid.")
            return False
        return True

    def run(self) -> Generator[MediaItem, None, None]:
        """Fetch media from mdblist and add them to media_items attribute
        if they are not already there"""
        items_to_yield = []
        try:
            for list in self.settings.lists:
                if not list:
                    continue

                if isinstance(list, int):
                    items = self.api.list_items_by_id(list)
                else:
                    items = self.api.list_items_by_url(list)
                for item in items:
                    if hasattr(item, "error") or not item or item.imdb_id is None:
                        continue
                    if item.imdb_id.startswith("tt"):
                        items_to_yield.append(MediaItem(
                            {"imdb_id": item.imdb_id, "requested_by": self.key}
                        ))
        except RateLimitExceeded:
            pass

        logger.info(f"Fetched {len(items_to_yield)} items from mdblist.com")
        yield items_to_yield

    def _calculate_request_time(self):
        limits = self.api.my_limits().limits
        daily_requests = limits.api_requests
        return daily_requests / 24 / 60 * 2