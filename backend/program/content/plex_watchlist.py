"""Plex Watchlist Module"""
from requests import ConnectTimeout
from utils.request import get, ping
from utils.logger import logger
from utils.settings import settings_manager as settings
from program.media import MediaItemContainer
from program.updaters.trakt import Updater as Trakt
import json


class PlexWatchlist:
    """Class for managing Plex watchlist"""

    def __init__(self, media_items: MediaItemContainer):
        self.initialized = False
        self.media_items = media_items
        self.watchlist_url = settings.get("plex")["watchlist"]
        if not self.watchlist_url or not self._validate_settings():
            logger.info(
                "Plex watchlist RSS URL is not configured and will not be used."
            )
            return
        self.updater = Trakt()
        self.initialized = True

    def _validate_settings(self):
        try:
            response = ping(
                self.watchlist_url,
                timeout=5,
            )
            return response.ok
        except ConnectTimeout:
            return False

    def run(self):
        """Fetch media from Plex watchlist and add them to media_items attribute
        if they are not already there"""
        items = self._get_items_from_plex_watchlist()
        new_items = [item for item in items if item not in self.media_items]
        container = self.updater.create_items(new_items)
        added_items = self.media_items.extend(container)
        if len(added_items) > 0:
            logger.info("Added %s items", len(added_items))

    def _get_items_from_plex_watchlist(self) -> list:
        """Fetch media from Plex watchlist"""
        response_obj = get(self.watchlist_url, timeout=5)
        watchlist_data = json.loads(response_obj.response.content)
        items = watchlist_data.get("items", [])
        ids = []
        for item in items:
            imdb_id = next(
                (
                    guid.split("//")[-1]
                    for guid in item.get("guids")
                    if "imdb://" in guid
                ),
                None,
            )
            ids.append(imdb_id)
        logger.debug("Found %s items", len(ids))
        return ids
