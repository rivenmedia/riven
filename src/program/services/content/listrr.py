"""Listrr content module"""
from typing import Generator

from kink import di

from program.apis.listrr_api import ListrrAPI
from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.utils.request import logger


class Listrr:
    """Content class for Listrr"""

    def __init__(self):
        self.key = "listrr"
        self.settings = settings_manager.settings.content.listrr
        self.api = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Listrr initialized!")

    def validate(self) -> bool:
        """Validate Listrr settings."""
        if not self.settings.enabled:
            return False
        if self.settings.api_key == "" or len(self.settings.api_key) != 64:
            logger.error("Listrr api key is not set or invalid.")
            return False
        valid_list_found = False
        for _, content_list in [
            ("movie_lists", self.settings.movie_lists),
            ("show_lists", self.settings.show_lists),
        ]:
            if content_list is None or not any(content_list):
                continue
            for item in content_list:
                if item == "" or len(item) != 24:
                    return False
            valid_list_found = True
        if not valid_list_found:
            logger.error("Both Movie and Show lists are empty or not set.")
            return False
        try:
            self.api = di[ListrrAPI]
            response = self.api.validate()
            if not response.is_ok:
                logger.error(
                    f"Listrr ping failed - Status Code: {response.status_code}, Reason: {response.response.reason}",
                )
            return response.is_ok
        except Exception as e:
            logger.error(f"Listrr ping exception: {e}")
            return False

    def run(self) -> Generator[MediaItem, None, None]:
        """Fetch new media from `Listrr`"""
        try:
            movie_items = self.api.get_items_from_Listrr("Movies", self.settings.movie_lists)
            show_items = self.api.get_items_from_Listrr("Shows", self.settings.show_lists)
        except Exception as e:
            logger.error(f"Failed to fetch items from Listrr: {e}")
            return

        imdb_ids = movie_items + show_items
        listrr_items = [MediaItem({"imdb_id": imdb_id, "requested_by": self.key}) for imdb_id in imdb_ids if imdb_id.startswith("tt")]
        logger.info(f"Fetched {len(listrr_items)} items from Listrr")
        yield listrr_items