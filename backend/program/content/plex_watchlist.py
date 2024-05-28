"""Plex Watchlist Module"""

from typing import Generator

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from requests import HTTPError
from utils.logger import logger
from utils.request import get, ping


class PlexWatchlist:
    """Class for managing Plex Watchlists"""

    def __init__(self):
        self.key = "plex_watchlist"
        self.rss_enabled = False
        self.settings = settings_manager.settings.content.plex_watchlist
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.token = settings_manager.settings.plex.token
        self.recurring_items = set()
        logger.success("Plex Watchlist initialized!")

    def validate(self):
        if not self.settings.enabled:
            logger.warning("Plex Watchlists is set to disabled.")
            return False
        if self.settings.rss:
            try:
                response = ping(self.settings.rss)
                response.raise_for_status()
                self.rss_enabled = True
                return True
            except HTTPError as e:
                if e.response.status_code == 404:
                    logger.warning("Plex RSS URL is Not Found. Please check your RSS URL in settings.")
                else:
                    logger.warning(
                        f"Plex RSS URL is not reachable (HTTP status code: {e.response.status_code}). Falling back to using user Watchlist."
                    )
                return True
            except Exception as e:
                logger.exception(f"Failed to validate Plex RSS URL: {e}")
                return True
        return True

    def run(self):
        """Fetch new media from `Plex Watchlist`"""
        if not self.rss_enabled:
            yield from self._get_items_from_watchlist()
        else:
            watchlist_items = set(self._get_items_from_watchlist())
            rss_items = set(self._get_items_from_rss())
            yield from (
                MediaItem({"imdb_id": imdb_id, "requested_by": self.key})
                for imdb_id in watchlist_items.union(rss_items)
            )


    def _get_items_from_rss(self) -> Generator[MediaItem, None, None]:
        """Fetch media from Plex RSS Feed."""
        try:
            response = get(self.settings.rss, timeout=60)
            if not response.is_ok:
                logger.error(f"Failed to fetch Plex RSS feed: HTTP {response.status_code}")
                return
            for item in response.data.items:
                for guid in item.guids:
                    if guid.startswith("imdb://"):
                        imdb_id = guid.split("//")[-1]
                        if imdb_id and imdb_id not in self.recurring_items:
                            self.recurring_items.add(imdb_id)
                            yield imdb_id
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching Plex RSS feed: {e}")
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
                if imdb_id and imdb_id not in self.recurring_items:
                    self.recurring_items.add(imdb_id)
                    yield imdb_id

    @staticmethod
    def _ratingkey_to_imdbid(ratingKey: str) -> str:
        """Convert Plex rating key to IMDb ID"""
        token = settings_manager.settings.plex.token
        filter_params = "includeGuids=1&includeFields=guid,title,year&includeElements=Guid"
        url = f"https://metadata.provider.plex.tv/library/metadata/{ratingKey}?X-Plex-Token={token}&{filter_params}"
        response = get(url)
        if response.is_ok and hasattr(response.data, "MediaContainer"):  # noqa: SIM102
            if hasattr(response.data.MediaContainer.Metadata[0], "Guid"):
                for guid in response.data.MediaContainer.Metadata[0].Guid:
                    if "imdb://" in guid.id:
                        return guid.id.split("//")[-1]
        logger.debug(f"Failed to fetch IMDb ID for ratingKey: {ratingKey}")
        return None
