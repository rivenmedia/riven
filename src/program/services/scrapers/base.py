import hashlib
from abc import abstractmethod
from typing import Any, Literal, TypeVar, cast

import bencodepy
import requests
from loguru import logger
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.utils.request import CircuitBreakerOpen, SmartSession, SmartResponse
from program.utils.torrent import extract_infohash
from program.core.runner import Runner
from program.settings.models import Observable

T = TypeVar("T", bound=Observable, covariant=True)


class ScraperService(Runner[T, "ScraperService", dict[str, str]]):
    """Base class for all scraper services.

    Implementations should set:
    - key: short identifier for the service (e.g., "torrentio")
    - initialized: bool set by validate()
    - timeout/settings as needed

    Optional attributes:
    - requires_imdb_id: whether the scraper needs an IMDb id to function
    """

    requires_imdb_id = False

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
    def scrape(self, item: MediaItem) -> dict[str, str]: ...

    @staticmethod
    def request_with_failover(
        session: SmartSession,
        urls: list[str],
        path: str,
        method: str = "GET",
        **kwargs: Any,
    ) -> SmartResponse | None:
        """
        Try each URL in order until one succeeds. Failover occurs on:
        - 429 rate limit responses
        - 5xx server errors
        - Connection errors / timeouts
        - Circuit breaker open

        Args:
            session: SmartSession instance to use for requests
            urls: List of base URLs to try in order
            path: Path to append to each URL
            method: HTTP method (default: GET)
            **kwargs: Additional arguments passed to session.request()

        Returns:
            SmartResponse if any URL succeeds, None if all fail
        """
        if not urls:
            logger.error("No URLs configured for scraper")
            return None

        last_exception: Exception | None = None
        last_response: SmartResponse | None = None

        for i, base_url in enumerate(urls):
            full_url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

            try:
                response = session.request(method, full_url, **kwargs)

                # Success - return immediately
                if response.ok:
                    if i > 0:
                        logger.debug(f"Failover succeeded: using URL #{i + 1}")
                    return response

                # Check for failover conditions
                if response.status_code == 429:
                    logger.debug(f"Rate limited on URL #{i + 1}, trying next URL...")
                    last_response = response
                    continue
                if response.status_code >= 500:
                    logger.debug(
                        f"Server error {response.status_code} on URL #{i + 1}, trying next URL..."
                    )
                    last_response = response
                    continue

                # Non-retryable error (4xx except 429) - return as-is
                return response

            except CircuitBreakerOpen as e:
                logger.debug(f"Circuit breaker open for URL #{i + 1}, trying next URL...")
                last_exception = e
                continue
            except requests.Timeout as e:
                logger.debug(f"Timeout on URL #{i + 1}, trying next URL...")
                last_exception = e
                continue
            except requests.ConnectionError as e:
                logger.debug(f"Connection error on URL #{i + 1}, trying next URL...")
                last_exception = e
                continue
            except Exception as e:
                logger.debug(f"Unexpected error on URL #{i + 1}: {e}")
                last_exception = e
                continue

        # All URLs failed
        if last_exception:
            logger.warning(f"All {len(urls)} URLs failed. Last error: {last_exception}")
        elif last_response:
            logger.warning(
                f"All {len(urls)} URLs failed. Last status: {last_response.status_code}"
            )
            return last_response

        return None

    @staticmethod
    def get_stremio_identifier(
        item: MediaItem,
    ) -> tuple[str | None, Literal["series", "movie"], str | None]:
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
    def get_infohash_from_url(url: str) -> str | None:
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
                    torrent_dict = cast(dict[bytes, bytes], bencodepy.decode(r.content))
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
