"""Plex Watchlist Module"""
from requests import HTTPError
from typing import Generator

from utils.request import get, ping
from utils.logger import logger
from program.settings.manager import settings_manager
from program.media.item import MediaItem


class PlexWatchlist():
    """Class for managing Plex Watchlists"""

    def __init__(self):
        self.key = "plex_watchlist"
        self.rss_enabled = False
        self.settings = settings_manager.settings.content.plex_watchlist
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.token = settings_manager.settings.plex.token
        self.not_found_ids = []
        logger.info("Plex Watchlist initialized!")

    def validate(self):
        if not self.settings.enabled:
            logger.debug("Plex Watchlists is set to disabled.")
            return False
        if self.settings.rss:
            try:
                response = ping(self.settings.rss)
                response.raise_for_status()
                self.rss_enabled = True
                return True
            except HTTPError as e:
                if e.response.status_code == 404:
                    logger.warn(
                        "Plex RSS URL is Not Found. Please check your RSS URL in settings."
                    )
                else:
                    logger.warn(
                        "Plex RSS URL is not reachable (HTTP status code: %s). Falling back to using user Watchlist.", e.response.status_codez
                    )
                return True
            except Exception as e:
                logger.exception("Failed to validate Plex RSS URL: %s", e)
                return True
        return True

    def run(self):
        """Fetch new media from `Plex Watchlist`"""
        self.not_found_ids.clear()
        if not self.rss_enabled:
            yield from self._get_items_from_watchlist()
        else:
            watchlist_items = set(self._get_items_from_watchlist())
            rss_items = set(self._get_items_from_rss())
            yield from (
                MediaItem({'imdb_id': id, 'requested_by': self.__class__}) 
                for id in watchlist_items.union(rss_items)
            )
            

    def _get_items_from_rss(self) -> Generator[MediaItem, None, None]:
        """Fetch media from Plex RSS Feed."""
        try:
            response = get(self.settings.rss, timeout=60)
            if not response.is_ok:
                logger.error(
                    "Failed to fetch Plex RSS feed: HTTP %s", response.status_code
                )
                return
            yield from (
                guid.split("//")[-1]
                for item in response.data.items
                for guid in item.guids
                if guid.startswith("imdb://")
            )
        except Exception as e:
            logger.error(
                "An unexpected error occurred while fetching Plex RSS feed: %s", e
            )
            
            return

    def _get_items_from_watchlist(self) -> Generator[MediaItem, None, None]:
        """Fetch media from Plex watchlist"""
        filter_params = "includeFields=title,year,ratingkey&includeElements=Guid&sort=watchlistedAt:desc"
        url = f"https://metadata.provider.plex.tv/library/sections/watchlist/all?X-Plex-Token={self.token}&{filter_params}"
        response = get(url)
        if not response.is_ok or not hasattr(response.data, "MediaContainer"):
            yield
            return
        for item in response.data.MediaContainer.Metadata:
            if hasattr(item, "ratingKey") and item.ratingKey:
                imdb_id = self._ratingkey_to_imdbid(item.ratingKey)
                if imdb_id:
                    yield imdb_id

    def _ratingkey_to_imdbid(self, ratingKey: str) -> str:
        """Convert Plex rating key to IMDb ID"""
        filter_params = (
            "includeGuids=1&includeFields=guid,title,year&includeElements=Guid"
        )
        url = f"https://metadata.provider.plex.tv/library/metadata/{ratingKey}?X-Plex-Token={self.token}&{filter_params}"
        response = get(url)
        if response.is_ok and hasattr(response.data, "MediaContainer"):
            if hasattr(response.data.MediaContainer.Metadata[0], "Guid"):
                for guid in response.data.MediaContainer.Metadata[0].Guid:
                    if "imdb://" in guid.id:
                        return guid.id.split("//")[-1]
        self.not_found_ids.append(ratingKey)
        return None
