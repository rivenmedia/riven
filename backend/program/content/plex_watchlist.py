"""Plex Watchlist Module"""
from time import time
from requests import HTTPError
from utils.request import get, ping
from utils.logger import logger
from program.settings.manager import settings_manager
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt


class PlexWatchlist:
    """Class for managing Plex Watchlists"""

    def __init__(self, media_items: MediaItemContainer):
        self.key = "plex_watchlist"
        self.rss_enabled = False
        self.settings = settings_manager.settings.content.plex_watchlist
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.token = settings_manager.settings.plex.token
        self.media_items = media_items
        self.updater = Trakt()
        self.not_found_ids = []
        self.next_run_time = 0
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
                    logger.warn("Plex RSS URL is Not Found. Please check your RSS URL in settings.")
                else:
                    logger.warn(f"Plex RSS URL is not reachable (HTTP status code: {e.response.status_code}). Falling back to using user Watchlist.")
                return True
            except Exception as e:
                logger.exception(f"Failed to validate Plex RSS URL: {e}")
                return True
        return True

    def run(self):
        """Fetch new media from `Plex Watchlist`"""
        if time() < self.next_run_time:
            return
        self.not_found_ids.clear()
        self.next_run_time = time() + self.settings.update_interval
        items = self._create_unique_list()
        new_items = [item for item in items if item not in self.media_items and not item]
        if not new_items:
            return
        container = self.updater.create_items(new_items)
        for item in container:
            item.set("requested_by", "Plex Watchlist")
        previous_count = len(self.media_items)
        self.media_items.extend(container)
        if len(self.media_items) > 0:
            if len(self.media_items) <= 5:
                for item in container:
                    logger.info("Added %s", item.log_string)
            else:
                logger.info("Added %s items", len(self.media_items) - previous_count)
        if self.not_found_ids:
            logger.warn("Failed to process %s items, skipping.", len(self.not_found_ids))

    def _create_unique_list(self):
        """Create a unique list of items from Plex RSS and Watchlist."""
        if not self.rss_enabled:
            return self._get_items_from_watchlist()
        watchlist_items = set(self._get_items_from_watchlist())
        rss_items = set(self._get_items_from_rss())
        unique_items = list(watchlist_items.union(rss_items))
        return unique_items

    def _get_items_from_rss(self) -> list:
        """Fetch media from Plex RSS Feed."""
        try:
            response = get(self.settings.rss, timeout=60)
            if not response.is_ok:
                logger.error(f"Failed to fetch Plex RSS feed: HTTP {response.status_code}")
                return []
            imdb_ids = [
                guid.split("//")[-1]
                for item in response.data.items
                for guid in item.guids
                if guid.startswith("imdb://")
            ]
            return imdb_ids
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching Plex RSS feed: {e}")
            return []

    def _get_items_from_watchlist(self) -> list:
        """Fetch media from Plex watchlist"""
        filter_params = "includeFields=title,year,ratingkey&includeElements=Guid&sort=watchlistedAt:desc"
        url = f"https://metadata.provider.plex.tv/library/sections/watchlist/all?X-Plex-Token={self.token}&{filter_params}"
        response = get(url)
        if response.is_ok and hasattr(response.data, "MediaContainer"):
            valid_items = filter(lambda item: hasattr(item, 'ratingKey') and item.ratingKey, response.data.MediaContainer.Metadata)
            imdb_ids = list(filter(None, map(lambda item: self._ratingkey_to_imdbid(item.ratingKey), valid_items)))
            return imdb_ids
        return []

    def _ratingkey_to_imdbid(self, ratingKey: str) -> str:
        """Convert Plex rating key to IMDb ID"""
        filter_params = "includeGuids=1&includeFields=guid,title,year&includeElements=Guid"
        url = f"https://metadata.provider.plex.tv/library/metadata/{ratingKey}?X-Plex-Token={self.token}&{filter_params}"
        response = get(url)
        if response.is_ok and hasattr(response.data, "MediaContainer"):
            if hasattr(response.data.MediaContainer.Metadata[0], "Guid"):
                for guid in response.data.MediaContainer.Metadata[0].Guid:
                    if "imdb://" in guid.id:
                        return guid.id.split("//")[-1]
        self.not_found_ids.append(ratingKey)
        return None
