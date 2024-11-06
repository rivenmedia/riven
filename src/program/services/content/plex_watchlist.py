"""Plex Watchlist Module"""
from typing import Generator

from kink import di
from loguru import logger
from requests import HTTPError

from program.apis.plex_api import PlexAPI
from program.media.item import MediaItem
from program.settings.manager import settings_manager


class PlexWatchlist:
    """Class for managing Plex Watchlists"""

    def __init__(self):
        self.key = "plex_watchlist"
        self.settings = settings_manager.settings.content.plex_watchlist
        self.api = None
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Plex Watchlist initialized!")

    def validate(self):
        if not self.settings.enabled:
            return False
        if not settings_manager.settings.updaters.plex.token:
            logger.error("Plex token is not set!")
            return False
        try:
            self.api = di[PlexAPI]
            self.api.validate_account()
        except Exception as e:
            logger.error(f"Unable to authenticate Plex account: {e}")
            return False
        if self.settings.rss:
            self.api.set_rss_urls(self.settings.rss)
            for rss_url in self.settings.rss:
                try:
                    response = self.api.validate_rss(rss_url)
                    response.response.raise_for_status()
                    self.api.rss_enabled = True
                except HTTPError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Plex RSS URL {rss_url} is Not Found. Please check your RSS URL in settings.")
                        return False
                    else:
                        logger.warning(
                            f"Plex RSS URL {rss_url} is not reachable (HTTP status code: {e.response.status_code})."
                        )
                        return False
                except Exception as e:
                    logger.error(f"Failed to validate Plex RSS URL {rss_url}: {e}", exc_info=True)
                    return False
        return True

    def run(self) -> Generator[MediaItem, None, None]:
        """Fetch new media from `Plex Watchlist` and RSS feed if enabled."""
        try:
            watchlist_items: list[str] = self.api.get_items_from_watchlist()
            rss_items: list[str] = self.api.get_items_from_rss() if self.api.rss_enabled else []
        except Exception as e:
            logger.warning(f"Error fetching items: {e}")
            return

        plex_items: set[str] = set(watchlist_items) | set(rss_items)
        items_to_yield: list[MediaItem] = [MediaItem({"imdb_id": imdb_id, "requested_by": self.key}) for imdb_id in plex_items if imdb_id and imdb_id.startswith("tt")]

        logger.info(f"Fetched {len(items_to_yield)} items from plex watchlist")
        yield items_to_yield