"""Plex Watchlist Module"""

from typing import Generator, Union

from program.media.item import Episode, MediaItem, Movie, Season, Show
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
            for rss_url in self.settings.rss:
                try:
                    response = ping(rss_url)
                    response.raise_for_status()
                    self.rss_enabled = True
                    return True
                except HTTPError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Plex RSS URL {rss_url} is Not Found. Please check your RSS URL in settings.")
                    else:
                        logger.warning(
                            f"Plex RSS URL {rss_url} is not reachable (HTTP status code: {e.response.status_code})."
                        )
                except Exception as e:
                    logger.error(f"Failed to validate Plex RSS URL {rss_url}: {e}", exc_info=True)
            logger.warning("None of the provided RSS URLs are reachable. Falling back to using user Watchlist.")
            return False
        return True

    def run(self) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Fetch new media from `Plex Watchlist` and RSS feed if enabled."""
        try:
            watchlist_items = set(self._get_items_from_watchlist())
            rss_items = set(self._get_items_from_rss()) if self.rss_enabled else set()
        except Exception as e:
            logger.error(f"Error fetching items: {e}")
            return

        new_items = watchlist_items | rss_items

        items = [
            MediaItem({"imdb_id": imdb_id, "requested_by": self.key})
            for imdb_id in new_items if imdb_id not in self.recurring_items
        ]
        for imdb_id in new_items:
            if imdb_id in self.recurring_items:
                continue
            self.recurring_items.add(imdb_id)

        yield items
    def _get_items_from_rss(self) -> Generator[MediaItem, None, None]:
        """Fetch media from Plex RSS Feeds."""
        for rss_url in self.settings.rss:
            try:
                response = get(rss_url, timeout=60)
                if not response.is_ok:
                    logger.error(f"Failed to fetch Plex RSS feed from {rss_url}: HTTP {response.status_code}")
                    continue
                for item in response.data.items:
                    yield from self._extract_imdb_ids(item.guids)
            except Exception as e:
                logger.error(f"An unexpected error occurred while fetching Plex RSS feed from {rss_url}: {e}")

    def _get_items_from_watchlist(self) -> Generator[MediaItem, None, None]:
        """Fetch media from Plex watchlist"""
        filter_params = "includeFields=title,year,ratingkey&includeElements=Guid&sort=watchlistedAt:desc"
        url = f"https://metadata.provider.plex.tv/library/sections/watchlist/all?X-Plex-Token={self.token}&{filter_params}"
        response = get(url)
        if not response.is_ok or not hasattr(response.data, "MediaContainer"):
            logger.error("Invalid response or missing MediaContainer in response data.")
            return
        media_container = getattr(response.data, "MediaContainer", None)
        if not media_container or not hasattr(media_container, "Metadata"):
            logger.error("MediaContainer is missing Metadata attribute.")
            return
        for item in media_container.Metadata:
            if hasattr(item, "ratingKey") and item.ratingKey:
                imdb_id = self._ratingkey_to_imdbid(item.ratingKey)
                if imdb_id:
                    yield imdb_id

    @staticmethod
    def _ratingkey_to_imdbid(ratingKey: str) -> str:
        """Convert Plex rating key to IMDb ID"""
        token = settings_manager.settings.plex.token
        filter_params = "includeGuids=1&includeFields=guid,title,year&includeElements=Guid"
        url = f"https://metadata.provider.plex.tv/library/metadata/{ratingKey}?X-Plex-Token={token}&{filter_params}"
        response = get(url)
        if response.is_ok and hasattr(response.data, "MediaContainer"):
            metadata = response.data.MediaContainer.Metadata[0]
            return next((guid.id.split("//")[-1] for guid in metadata.Guid if "imdb://" in guid.id), None)
        logger.debug(f"Failed to fetch IMDb ID for ratingKey: {ratingKey}")
        return None

    def _extract_imdb_ids(self, guids):
        """Helper method to extract IMDb IDs from guids"""
        for guid in guids:
            if guid.startswith("imdb://"):
                imdb_id = guid.split("//")[-1]
                if imdb_id:
                    yield imdb_id
