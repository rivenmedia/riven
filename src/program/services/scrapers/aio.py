"""AIO scraper module"""

import base64

from loguru import logger
from pydantic import BaseModel, Field
from requests import HTTPError

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.settings.models import AIOConfig
from program.utils.request import SmartSession, get_hostname_from_url


class AIOSearchResult(BaseModel):
    """Model for a single AIO search result"""

    info_hash: str | None = Field(alias="infoHash")
    filename: str | None = None
    folder_name: str | None = Field(default=None, alias="folderName")


class AIOSearchData(BaseModel):
    """Model for AIO search response data"""

    results: list[AIOSearchResult]


class AIOSearchResponse(BaseModel):
    """Model for AIO search response"""

    success: bool
    data: AIOSearchData | None = None


class AIO(ScraperService[AIOConfig]):
    """Scraper for `AIOStreams`"""

    requires_imdb_id = True

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.scraping.aio
        self.timeout = self.settings.timeout or 30

        self.session = SmartSession(
            rate_limits=(
                {
                    get_hostname_from_url(self.settings.url): {
                        # taken from official defaults https://github.com/Viren070/AIOStreams/blob/main/.env.sample
                        "rate": 10 / 5,  # 10 requests per 5 seconds (Stream API default)
                        "capacity": 10,
                    }
                }
                if self.settings.ratelimit
                else None
            ),
            retries=self.settings.retries,
            backoff_factor=0.3,
        )

        self.proxies = (
            {"http": self.settings.proxy_url, "https": self.settings.proxy_url}
            if self.settings.proxy_url
            else None
        )

        self._initialize()

    def _get_auth_header(self) -> dict[str, str]:
        """Generate Basic Auth header from uuid and password."""
        credentials = f"{self.settings.uuid}:{self.settings.password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    def validate(self) -> bool:
        """Validate the AIO settings."""

        if not self.settings.enabled:
            return False

        if not self.settings.url:
            logger.error("AIO URL is not configured and will not be used.")
            return False

        if not self.settings.uuid or not self.settings.password:
            logger.error(
                "AIO uuid and password are required for authentication and will not be used."
            )
            return False

        if self.timeout <= 0:
            logger.error("AIO timeout must be a positive integer.")
            return False

        try:
            # Test connection with a simple search
            url = f"{self.settings.url.rstrip('/')}/api/v1/search"
            params = {"type": "movie", "id": "tt0111161", "requiredFields": "infoHash"}
            headers = self._get_auth_header()

            response = self.session.get(
                url, params=params, timeout=10, headers=headers, proxies=self.proxies
            )

            if not response.ok:
                logger.error(f"AIO validation failed with status {response.status_code}")
                return False

            data = response.json()
            if not data.get("success", False):
                error = data.get("error", {})
                logger.error(
                    f"AIO validation failed: {error.get('message', 'Unknown error')}"
                )
                return False

            return True
        except Exception as e:
            logger.error(f"AIO failed to initialize: {e}")
            return False

    def run(self, item: MediaItem) -> dict[str, str]:
        """Scrape AIO with the given media item for streams"""

        try:
            return self.scrape(item)
        except HTTPError as http_err:
            if http_err.response.status_code == 429:
                logger.debug(f"AIO rate limit exceeded for item: {item.log_string}")
            else:
                logger.error(f"AIO HTTP error for {item.log_string}: {str(http_err)}")
        except Exception as e:
            logger.exception(f"AIO exception thrown: {str(e)}")

        return {}

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Wrapper for `AIO` scrape method"""

        if isinstance(item, Movie):
            imdb_id = item.imdb_id
            search_id = imdb_id  # tt1234567
            aio_type = "anime" if item.is_anime else "movie"
        elif isinstance(item, Show):
            imdb_id = item.imdb_id
            search_id = f"{imdb_id}:1:1"  # tt1234567:1:1
            aio_type = "anime" if item.is_anime else "series"
        elif isinstance(item, Season):
            imdb_id = item.parent.imdb_id
            search_id = f"{imdb_id}:{item.number}:1"  # tt1234567:season:1
            aio_type = "anime" if item.parent.is_anime else "series"
        elif isinstance(item, Episode):
            imdb_id = item.parent.parent.imdb_id
            search_id = f"{imdb_id}:{item.parent.number}:{item.number}"  # tt1234567:season:episode
            aio_type = "anime" if item.parent.parent.is_anime else "series"
        else:
            return {}

        logger.trace(f"Scraping AIO for {item.log_string}, imdb_id: {imdb_id}, search_id: {search_id}, aio_type: {aio_type}")

        if not imdb_id:
            return {}

        url = f"{self.settings.url.rstrip('/')}/api/v1/search"
        params = {
            "type": aio_type,
            "id": search_id,
            "requiredFields": "infoHash",
        }
        headers = self._get_auth_header()

        response = self.session.get(
            url,
            params=params,
            timeout=self.timeout,
            headers=headers,
            proxies=self.proxies,
        )

        if not response.ok:
            response.raise_for_status()
            logger.error(f"AIO request failed for {item.log_string}: {response.text}")
            return {}

        data = AIOSearchResponse.model_validate(response.json())

        if not data.success or not data.data:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        if not data.data.results:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = dict[str, str]()

        for result in data.data.results:
            if not result.info_hash:
                continue

            # Use filename or folder_name as the raw title
            raw_title = result.folder_name or result.filename
            if not raw_title:
                continue

            torrents[result.info_hash] = raw_title

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
