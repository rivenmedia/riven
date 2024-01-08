"""Plex Watchlist Module"""
from typing import Optional
from pydantic import BaseModel
from requests import ConnectTimeout
from utils.request import get, ping
from utils.logger import logger
from utils.settings import settings_manager
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt
import json


class PlexWatchlistConfig(BaseModel):
    enabled: bool
    rss: Optional[str]


class PlexWatchlist:
    """Class for managing Plex Watchlists"""

    def __init__(self, media_items: MediaItemContainer):
        self.key = "plex_watchlist"
        self.rss_enabled = False
        self.settings = PlexWatchlistConfig(**settings_manager.get(f"content.{self.key}"))
        self.initialized = self.validate_settings()
        if not self.initialized:
            return
        self.token = settings_manager.get("plex.token")
        self.media_items = media_items
        self.prev_count = 0
        self.updater = Trakt()

    def validate_settings(self):
        if not self.settings.enabled:
            logger.debug("Plex Watchlists is set to disabled.")
            return False
        if self.settings.rss:
            try:
                response = ping(self.settings.rss, timeout=15)
                if response.ok:
                    self.rss_enabled = True
                    return True
                else:
                    logger.warn(f"Plex RSS URL is not reachable. Falling back to normal Watchlist.")
                    return True
            except Exception:
                return False
        return True

    def run(self):
        """Fetch media from Plex Watchlist and add them to media_items attribute
        if they are not already there"""
        items = self._create_unique_list()
        new_items = [item for item in items if item not in self.media_items]
        container = self.updater.create_items(new_items)
        for item in container:
            item.set("requested_by", "Plex Watchlist")
        previous_count = len(self.media_items)
        added_items = self.media_items.extend(container)
        added_items_count = len(self.media_items) - previous_count
        if (
            added_items_count != self.prev_count
        ):
            self.prev_count = added_items_count
        length = len(added_items)
        if length >= 1 and length <= 5:
            for item in added_items:
                logger.info("Added %s", item.log_string)
        elif length > 5:
            logger.info("Added %s items", length)

    def _create_unique_list(self):
        """Create a unique list of items from Plex RSS and Watchlist"""
        watchlist_items = self._get_items_from_watchlist()
        if not self.rss_enabled:
            return watchlist_items
        rss_items = self._get_items_from_rss()
        return list(set(watchlist_items).union(rss_items))

    def _get_items_from_rss(self) -> list:
        """Fetch media from Plex RSS Feed"""
        try:
            response_obj = get(self.settings.rss, timeout=30)
            data = json.loads(response_obj.response.content)
            items = data.get("items", [])
            ids = [
                guid.split("//")[-1]
                for item in items
                for guid in item.get("guids", [])
                if "imdb://" in guid
            ]
            return ids
        except ConnectTimeout:
            logger.error("Connection Timeout: Failed to fetch Plex RSS feed")
            return []
        except Exception:
            logger.exception("Failed to fetch Plex RSS feed")
            return []

    def _get_items_from_watchlist(self) -> list:
        """Fetch media from Plex watchlist"""
        filter_params = "includeFields=title,year,ratingkey&includeElements=Guid&sort=watchlistedAt:desc"
        url = f"https://metadata.provider.plex.tv/library/sections/watchlist/all?X-Plex-Token={self.token}&{filter_params}"
        response = get(url)
        if not response.is_ok:
            return []
        ids = []
        for item in response.data.MediaContainer.Metadata:
            if not item.ratingKey:
                continue
            imdb_id = self._ratingkey_to_imdbid(item.ratingKey)
            if imdb_id:
                ids.append(imdb_id)
        return ids

    def _ratingkey_to_imdbid(self, ratingKey: str) -> str:
        """Convert Plex rating key to IMDb ID"""
        filter_params = "includeGuids=1&includeFields=guid,title,year&includeElements=Guid"
        url = f"https://metadata.provider.plex.tv/library/metadata/{ratingKey}?X-Plex-Token={self.token}&{filter_params}"
        response = get(url)
        if not response.is_ok:
            return None
        metadata = response.data.MediaContainer.Metadata
        if not metadata or not hasattr(metadata[0], "Guid"):
            return None
        for guid in metadata[0].Guid:
            if "imdb://" in guid.id:
                return guid.id.split("//")[-1]
        return None
