"""Plex Watchlist Module"""
from requests import ConnectTimeout
from utils.request import get, ping
from utils.logger import logger
from utils.settings import settings_manager as settings
from program.media import MediaItemContainer
from program.updaters.trakt import Updater as Trakt
import json


class Content:
    """Class for managing Plex watchlist"""

    def __init__(self):
        self.initialized = False
        self.watchlist_url = settings.get("plex")["watchlist"]
        if not self.watchlist_url or not self._validate_settings():
            logger.info("Plex watchlist RSS URL is not configured and will not be used.")
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

    def update_items(self, media_items: MediaItemContainer):
        """Fetch media from Plex watchlist and add them to media_items attribute
        if they are not already there"""
        logger.info("Getting items...")
        items = self._get_items_from_plex_watchlist()
        new_items = [item for item in items if item not in media_items]
        container = self.updater.create_items(new_items)
        added_items = media_items.extend(container)
        if len(added_items) > 0:
            logger.info("Added %s items", len(added_items))
        logger.info("Done!")

    def _get_items_from_plex_watchlist(self) -> list:
        """Fetch media from Plex watchlist"""
        response_obj = get(self.watchlist_url, timeout=5)
        watchlist_data = json.loads(response_obj.response.content)
        items = watchlist_data.get('items', [])
        ids = []
        for item in items:
            imdb_id = next((guid.split('//')[-1] for guid in item.get('guids') if "imdb://" in guid), None)
            ids.append(imdb_id)
        return ids
