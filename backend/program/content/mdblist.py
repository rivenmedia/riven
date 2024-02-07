"""Mdblist content module"""
from time import time
from utils.logger import logger
from program.settings.manager import settings_manager
from program.media.container import MediaItemContainer
from utils.request import RateLimitExceeded, RateLimiter, get, ping
from program.content.base import ContentServiceBase


class Mdblist(ContentServiceBase):
    """Content class for mdblist"""

    def __init__(self, media_items: MediaItemContainer):
        self.key = "mdblist"
        self.settings = settings_manager.settings.content.mdblist
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.requests_per_2_minutes = self._calculate_request_time()
        self.rate_limiter = RateLimiter(self.requests_per_2_minutes, 120, True)
        super().__init__(media_items)
        logger.info("mdblist initialized")

    def validate(self):
        if not self.settings.enabled:
            logger.debug("Mdblist is set to disabled.")
            return False
        if self.settings.lists == [""]:
            logger.error("Mdblist is enabled, but list is empty.")
            return False
        if self.settings.api_key == "" or len(self.settings.api_key) != 25:
            logger.error("Mdblist api key is not set.")
            return False
        response = ping(f"https://mdblist.com/api/user?apikey={self.settings.api_key}")
        if "Invalid API key!" in response.text:
            logger.error("Mdblist api key is invalid.")
            return False
        return True

    def run(self):
        """Fetch media from mdblist and add them to media_items attribute
        if they are not already there"""
        if time() < self.next_run_time:
            return
        self.next_run_time = time() + self.settings.update_interval
        try:
            with self.rate_limiter:
                items = MediaItemContainer()
                for list_id in self.settings.lists:
                    if list_id:
                        items.extend(self._get_items_from_list(list_id, self.settings.api_key))
                added_items = self.process_items(items, "Mdblist")
                if not added_items:
                    return
                length = len(added_items)
                if length >= 1 and length <= 5:
                    for item in added_items:
                        logger.info("Added %s", item.log_string)
                elif length > 5:
                    logger.info("Added %s items", length)
        except RateLimitExceeded:
            pass

    def _get_items_from_list(self, list_id: str, api_key: str) -> MediaItemContainer:
        return [item.imdb_id for item in list_items(list_id, api_key)]

    def _calculate_request_time(self):
        limits = my_limits(self.settings.api_key).limits
        daily_requests = limits.api_requests
        requests_per_2_minutes = daily_requests / 24 / 60 * 2
        return requests_per_2_minutes


# API METHODS


def my_limits(api_key: str):
    """Wrapper for mdblist api method 'My limits'"""
    response = get(f"http://www.mdblist.com/api/user?apikey={api_key}")
    return response.data


def list_items(list_id: str, api_key: str):
    """Wrapper for mdblist api method 'List items'"""
    response = get(f"http://www.mdblist.com/api/lists/{list_id}/items?apikey={api_key}")
    return response.data
