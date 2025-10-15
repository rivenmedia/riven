import hashlib
from abc import ABC, abstractmethod
from base64 import decode, encode
from typing import Dict, Tuple

from loguru import logger
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.utils.request import SmartSession


class ScraperService(ABC):
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
    def run(self, item: MediaItem) -> Dict[str, str]: ...

    @abstractmethod
    def scrape(self, item: MediaItem) -> Dict[str, str]: ...

    @staticmethod
    def get_stremio_identifier(item: MediaItem) -> Tuple[str | None, str, str]:
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
            return None, None, None
        return identifier, scrape_type, imdb_id

    @staticmethod
    def get_infohash_from_torrent_url(url: str) -> str:
        """Get the infohash from a torrent URL"""
        session = SmartSession()
        with session.get(url, stream=True) as r:
            r.raise_for_status()
            torrent_data = r.content
            torrent_dict = decode(torrent_data)
            info = torrent_dict[b"info"]
            infohash = hashlib.sha1(encode(info)).hexdigest()
        return infohash
