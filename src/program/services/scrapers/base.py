import hashlib
from abc import abstractmethod
from typing import Optional, TypeVar

import bencodepy
from loguru import logger
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.utils.request import SmartSession
from program.utils.torrent import extract_infohash
from program.core.runner import Runner
from program.settings.models import Observable

T = TypeVar("T", bound=Observable)


class ScraperService(Runner[T]):
    """Base class for all scraper services.

    Implementations should set:
    - key: short identifier for the service (e.g., "torrentio")
    - initialized: bool set by validate()
    - timeout/settings as needed

    Optional attributes:
    - requires_imdb_id: whether the scraper needs an IMDb id to function
    """

    requires_imdb_id: bool = False

    def __init__(self, service_name):
        self.key = service_name
        self.initialized = False

    def _initialize(self) -> None:
        try:
            if self.validate():
                self.initialized = True
                logger.success(f"{self.__class__.__name__} scraper initialized")
        except Exception:
            pass

    @abstractmethod
    def validate(self) -> bool: ...

    @abstractmethod
    def run(self, item: MediaItem) -> dict[str, str]: ...

    @abstractmethod
    def scrape(self, item: MediaItem) -> dict[str, str]: ...

    @staticmethod
    def get_stremio_identifier(item: MediaItem) -> tuple[str | None, str, str]:
        """
        Get the Stremio identifier for a given item.

        Returns:
            Tuple[str | None, str, str]: (identifier, scrape_type, imdb_id)
        """

        if isinstance(item, Show):
            identifier, scrape_type, imdb_id = ":1:1", "series", item.imdb_id
        elif isinstance(item, Season):
            identifier, scrape_type, imdb_id = (
                f":{item.number}:1",
                "series",
                item.parent.imdb_id,
            )
        elif isinstance(item, Episode):
            identifier, scrape_type, imdb_id = (
                f":{item.parent.number}:{item.number}",
                "series",
                item.parent.parent.imdb_id,
            )
        elif isinstance(item, Movie):
            identifier, scrape_type, imdb_id = None, "movie", item.imdb_id
        else:
            raise ValueError("Unsupported MediaItem type")

        return identifier, scrape_type, imdb_id

    @staticmethod
    def get_infohash_from_url(url: str) -> Optional[str]:
        """
        Get infohash from a URL that could be:
        1. A direct torrent file download
        2. A redirect to a magnet link
        3. A URL containing the infohash

        Returns the infohash or None if it cannot be extracted.
        """
        if not url:
            return None

        session = SmartSession()
        try:
            # Try to download with redirects disabled to check for magnet redirects
            r = session.get(url, allow_redirects=False)

            # If it's a redirect (3xx status code)
            if 300 <= r.status_code < 400:
                location = r.headers.get("Location", "")
                if location:
                    # Check if the redirect is a magnet link and extract infohash
                    infohash = extract_infohash(location)
                    if infohash:
                        return infohash

            # If it's a successful response, try to parse as torrent file
            if r.status_code == 200:
                try:
                    torrent_dict = bencodepy.decode(r.content)
                    info = torrent_dict[b"info"]
                    infohash = hashlib.sha1(bencodepy.encode(info)).hexdigest()
                    return infohash.lower()
                except Exception:
                    # Not a valid torrent file, try to extract from URL
                    pass

            # Try to extract infohash from the URL itself (handles magnets and bare hashes)
            infohash = extract_infohash(url)
            if infohash:
                return infohash

        except Exception as e:
            logger.debug(f"Failed to get infohash from URL {url}: {e}")

        return None
