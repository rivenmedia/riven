"""Plex Watchlist Module"""
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from typing import Generator, Union

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from program.indexers.trakt import get_imdbid_from_tvdb
from requests import HTTPError
from utils.logger import logger
from utils.request import get, ping
from plexapi.myplex import MyPlexAccount
from requests import Session
import xmltodict


class PlexWatchlist:
    """Class for managing Plex Watchlists"""

    def __init__(self):
        self.key = "plex_watchlist"
        self.rss_enabled = False
        self.settings = settings_manager.settings.content.plex_watchlist
        self.token = settings_manager.settings.updaters.plex.token
        self.account = None
        self.session = Session()
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.recurring_items = set()
        logger.success("Plex Watchlist initialized!")

    def validate(self):
        if not self.settings.enabled:
            logger.warning("Plex Watchlists is set to disabled.")
            return False
        if not self.token:
            logger.error("Plex token is not set!")
            return False
        try:
            self.account = MyPlexAccount(self.session, token=self.token)
        except Exception as e:
            logger.error(f"Unable to authenticate Plex account: {e}")
            return False
        if self.settings.rss:
            for rss_url in self.settings.rss:
                try:
                    response = ping(rss_url)
                    response.response.raise_for_status()
                    self.rss_enabled = True
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

    def run(self) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Fetch new media from `Plex Watchlist` and RSS feed if enabled."""
        try:
            watchlist_items = set(self._get_items_from_watchlist())
            rss_items = set(self._get_items_from_rss()) if self.rss_enabled else set()
        except Exception as e:
            logger.error(f"Error fetching items: {e}")
            return

        new_items = watchlist_items | rss_items

        for imdb_id in new_items:
            if not imdb_id or imdb_id in self.recurring_items:
                continue
            self.recurring_items.add(imdb_id)
            media_item = MediaItem({"imdb_id": imdb_id, "requested_by": self.key})
            if media_item:
                yield media_item
            else:
                logger.log("NOT_FOUND", f"Failed to create media item for {imdb_id}")


    def _get_items_from_rss(self) -> Generator[MediaItem, None, None]:
        """Fetch media from Plex RSS Feeds."""
        for rss_url in self.settings.rss:
            try:
                response = self.session.get(rss_url, timeout=60)
                if not response.ok:
                    logger.error(f"Failed to fetch Plex RSS feed from {rss_url}: HTTP {response.status_code}")
                    continue

                xmltodict_data = xmltodict.parse(response.content)
                items = xmltodict_data.get("rss", {}).get("channel", {}).get("item", [])
                for item in items:
                    guid_text = item.get("guid", {}).get("#text", "")
                    guid_id = guid_text.split("//")[-1] if guid_text else ""
                    if not guid_id or guid_id in self.recurring_items:
                        continue
                    if guid_id.startswith("tt") and guid_id not in self.recurring_items:
                        yield guid_id
                    elif guid_id:
                        imdb_id: str = get_imdbid_from_tvdb(guid_id)
                        if not imdb_id or not imdb_id.startswith("tt") or imdb_id in self.recurring_items:
                            continue
                        yield imdb_id
                    else:
                        logger.log("NOT_FOUND", f"Failed to extract IMDb ID from {item['title']}")
                        continue
            except Exception as e:
                logger.error(f"An unexpected error occurred while fetching Plex RSS feed from {rss_url}: {e}")
                continue

    def _get_items_from_watchlist(self) -> Generator[MediaItem, None, None]:
        """Fetch media from Plex watchlist"""
        # filter_params = "includeFields=title,year,ratingkey&includeElements=Guid&sort=watchlistedAt:desc"
        # url = f"https://metadata.provider.plex.tv/library/sections/watchlist/all?X-Plex-Token={self.token}&{filter_params}"
        # response = get(url)
        items = self.account.watchlist()
        for item in items:
            if hasattr(item, "guids") and item.guids:
                imdb_id = next((guid.id.split("//")[-1] for guid in item.guids if guid.id.startswith("imdb://")), None)
                if imdb_id and imdb_id in self.recurring_items:
                    continue
                elif imdb_id.startswith("tt"):
                    yield imdb_id
                else:
                    logger.log("NOT_FOUND", f"Unable to extract IMDb ID from {item.title} ({item.year}) with data id: {imdb_id}")
            else:
                logger.log("NOT_FOUND", f"{item.title} ({item.year}) is missing guids attribute from Plex")

    @staticmethod
    def _ratingkey_to_imdbid(ratingKey: str) -> str:
        """Convert Plex rating key to IMDb ID"""
        token = settings_manager.settings.updaters.plex.token
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
                    return imdb_id