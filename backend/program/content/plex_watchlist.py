"""Plex Watchlist Module"""
from requests import ConnectTimeout
from utils.request import get, ping
from utils.logger import logger
from utils.settings import settings_manager as settings
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt
import json


class PlexWatchlist:
    """Class for managing Plex watchlist"""

    def __init__(self, media_items: MediaItemContainer):
        self.key = "plex_watchlist"
        self.url = settings.get("plex.watchlist_url")
        self.initialized = False
        self.media_items = media_items
        self.previous_added_items_count = 0
        if not self.url or not self._validate_settings():
            logger.info("Plex Watchlist is not configured and will not be used.")
            return
        self.updater = Trakt()
        self.initialized = True

    def _validate_settings(self):
        if self.url == "":
            return False
        try:
            response = ping(
                self.url,
                timeout=10,
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
        for item in container:
            item.set("requested_by", "Plex Watchlist")
        previous_count = len(self.media_items)
        added_items = self.media_items.extend(container)
        added_items_count = len(self.media_items) - previous_count
        if (
            added_items_count != self.previous_added_items_count
            and added_items_count > 0
        ):
            logger.info("Added %s items", added_items_count)
            self.previous_added_items_count = added_items_count
        if added_items_count > 0:
            for added_item in added_items:
                logger.debug("Added %s", added_item.title)

    def _get_items_from_plex_watchlist(self) -> list:
        """Fetch media from Plex watchlist"""
        response_obj = get(self.url, timeout=30)
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
            if imdb_id:
                ids.append(imdb_id)
            else:
                logger.warning(
                    "Could not find IMDb ID for %s in Plex watchlist", item.get("title")
                )
        return ids
