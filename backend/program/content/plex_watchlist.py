"""Plex Watchlist Module"""
from typing import Optional
from pydantic import BaseModel
from requests import ConnectTimeout, HTTPError
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
        self.not_found_ids = []

    def validate_settings(self):
        if not self.settings.enabled:
            logger.debug("Plex Watchlists is set to disabled.")
            return False
        if self.settings.rss:
            logger.info("Found Plex RSS URL. Validating...")
            try:
                response = ping(self.settings.rss)
                if response.ok:
                    self.rss_enabled = True
                    logger.info("Plex RSS URL is valid.")
                    return True
                else:
                    logger.info(f"Plex RSS URL is not valid. Falling back to watching user Watchlist.")
                    return True
            except HTTPError as e:
                if e.response.status_code in [404]:
                    logger.warn("Plex RSS URL is Not Found. Falling back to watching user Watchlist.")
                    return True
                if e.response.status_code >= 400 and e.response.status_code <= 499:
                    logger.warn(f"Plex RSS URL is not reachable. Falling back to watching user Watchlist.")
                    return True
                if e.response.status_code >= 500:
                    logger.error(f"Plex is having issues validating RSS feed. Falling back to watching user Watchlist.")
                    return True
            except Exception as e:
                logger.exception("Failed to validate Plex RSS URL: %s", e)
                return True
        return True

    def run(self):
        """Fetch media from Plex Watchlist and add them to media_items attribute
        if they are not already there"""
        items = self._create_unique_list()
        new_items = [item for item in items if item not in self.media_items] or []
        if len(new_items) == 0:
            logger.debug("No new items found in Plex Watchlist")
            return
        for check in new_items:
            if check is None:
                new_items.remove(check)
                self.not_found_ids.append(check)
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
        if len(self.not_found_ids) >= 1 and len(self.not_found_ids) <= 5:
            for item in self.not_found_ids:
                logger.info("Failed to add %s", item)

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
            response_obj = get(self.settings.rss, timeout=60)
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
