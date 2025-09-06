from typing import Dict, List, Optional, Union

from loguru import logger
from plexapi.library import LibrarySection
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer

from program.media import Movie, Episode
from program.settings.manager import settings_manager
from program.utils.request import SmartSession


class PlexAPIError(Exception):
    """Base exception for PlexApi related errors"""

class PlexAPI:
    """Handles Plex API communication"""

    def __init__(self, token: str, base_url: str):
        self.rss_urls: Optional[List[str]] = None
        self.token = token
        self.BASE_URL = base_url

        rate_limits = {
            "metadata.provider.plex.tv": {"rate": 1, "capacity": 60},  # 1 call per second, 60 calls per minute
        }

        self.session = SmartSession(
            rate_limits=rate_limits,
            retries=3,
            backoff_factor=0.3
        )

        self.account = None
        self.plex_server = None
        self.rss_enabled = False

    def validate_account(self):
        try:
            self.account = MyPlexAccount(session=self.session, token=self.token)
        except Exception as e:
            logger.error(f"Failed to authenticate Plex account: {e}")
            return False
        return True

    def validate_server(self):
        self.plex_server = PlexServer(self.BASE_URL, token=self.token, session=self.session, timeout=60)

    def set_rss_urls(self, rss_urls: List[str]):
        self.rss_urls = rss_urls

    def clear_rss_urls(self):
        self.rss_urls = None
        self.rss_enabled = False

    def validate_rss(self, url: str):
        return self.session.get(url)

    def ratingkey_to_imdbid(self, ratingKey: str) -> str | None:
        """Convert Plex rating key to IMDb ID"""
        token = settings_manager.settings.updaters.plex.token
        filter_params = "includeGuids=1&includeFields=guid,title,year&includeElements=Guid"
        url = f"https://metadata.provider.plex.tv/library/metadata/{ratingKey}?X-Plex-Token={token}&{filter_params}"
        response = self.session.get(url)
        if response.ok and hasattr(response.data, "MediaContainer"):
            metadata = response.data.MediaContainer.Metadata[0]
            return next((guid.id.split("//")[-1] for guid in metadata.Guid if "imdb://" in guid.id), None)
        logger.debug(f"Failed to fetch IMDb ID for ratingKey: {ratingKey}")
        return None

    def get_items_from_rss(self) -> list[str]:
        """Fetch media from Plex RSS Feeds."""
        rss_items: list[str] = []
        for rss_url in self.rss_urls:
            try:
                response = self.session.get(rss_url + "?format=json", timeout=60)
                if not response.ok or not hasattr(response.data, "items"):
                    logger.error(f"Failed to fetch Plex RSS feed from {rss_url}")
                    continue

                for _item in response.data.items:
                    imdb_id = self.extract_imdb_ids(_item.get("guids", []))
                    if imdb_id and imdb_id.startswith("tt"):
                        rss_items.append(imdb_id)
                    else:
                        logger.log("NOT_FOUND", f"Failed to extract IMDb ID from {_item['title']}")
            except Exception as e:
                logger.error(f"An unexpected error occurred while fetching Plex RSS feed from {rss_url}: {e}")
        return rss_items

    def get_items_from_watchlist(self) -> list[dict[str, Optional[str]]]:
        """Fetch media from Plex watchlist"""
        items = self.account.watchlist()
        watchlist_items: list[dict[str, str]] = []
        for item in items:
            try:
                imdb_id = None
                tmdb_id = None
                tvdb_id = None

                if hasattr(item, "guids") and item.guids:
                    imdb_id: str = next((guid.id.split("//")[-1] for guid in item.guids if guid.id.startswith("imdb://")), "")
                    if item.TYPE == "movie":
                        tmdb_id: str = next((guid.id.split("//")[-1] for guid in item.guids if guid.id.startswith("tmdb://")), "")
                    elif item.TYPE == "show":
                        tvdb_id: str = next((guid.id.split("//")[-1] for guid in item.guids if guid.id.startswith("tvdb://")), "")

                    if not any([imdb_id, tmdb_id, tvdb_id]):
                        logger.log("NOT_FOUND", f"Unable to extract IMDb ID from {item.title} ({item.year}) with data id: {imdb_id}")
                        continue

                    watchlist_items.append({"imdb_id": imdb_id, "tmdb_id": tmdb_id, "tvdb_id": tvdb_id})
                else:
                    logger.log("NOT_FOUND", f"{item.title} ({item.year}) is missing guids attribute from Plex")
            except Exception as e:
                logger.error(f"An unexpected error occurred while fetching Plex watchlist item {item.title}: {e}")

        return watchlist_items

    def extract_imdb_ids(self, guids: list) -> str | None:
        """Helper method to extract IMDb IDs from guids"""
        for guid in guids:
            if guid and guid.startswith("imdb://"):
                imdb_id = guid.split("//")[-1]
                if imdb_id:
                    return imdb_id
        return None

    def update_section(self, section, item: Union[Movie, Episode]) -> bool:
        """Update the Plex section for the given item"""
        if item.update_folder and item.update_folder != "updated":
            update_folder = item.update_folder
            section.update(str(update_folder))
            return True
        return False

    def map_sections_with_paths(self) -> Dict[LibrarySection, List[str]]:
        """Map Plex sections with their paths"""
        # Skip sections without locations and non-movie/show sections
        sections = [section for section in self.plex_server.library.sections() if section.type in ["show", "movie"] and section.locations]
        # Map sections with their locations with the section obj as key and the location strings as values
        return {section: section.locations for section in sections}