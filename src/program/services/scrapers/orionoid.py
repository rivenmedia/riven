"""Orionoid scraper module"""

from loguru import logger
from pydantic import BaseModel, ValidationError

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.scrapers.base import ScraperService
from program.settings import settings_manager
from program.utils.request import CircuitBreakerOpen, SmartSession
from program.settings.models import OrionoidConfig

KEY_APP = "D3CH6HMX9KD9EMD68RXRCDUNBDJV5HRR"


class OrionoidErrorResponse(BaseModel):
    class Result(BaseModel):
        status: str
        message: str

    result: Result


class OrionoidAuthResponse(BaseModel):
    class Result(BaseModel):
        status: str

    class Data(BaseModel):
        class Subscription(BaseModel):
            class Package(BaseModel):
                type: str
                premium: bool

            package: Package

        class Service(BaseModel):
            realdebrid: bool

        class Requests(BaseModel):
            class Streams(BaseModel):
                class Daily(BaseModel):
                    remaining: int | None

                daily: Daily

            streams: Streams

        requests: Requests
        status: str
        subscription: Subscription
        service: Service

    result: Result
    data: Data

    @property
    def is_premium(self) -> bool:
        """Check if the user has a premium plan."""

        if not self.data:
            return False

        active = self.data.status == "active"
        premium = self.data.subscription.package.premium
        debrid = self.data.service.realdebrid

        return active and premium and debrid

    @property
    def is_unlimited(self) -> bool:
        """Check if the user has an unlimited plan."""

        if not self.data:
            return False

        return self.data.subscription.package.type == "unlimited"


class OrionoidScrapeParams(BaseModel):
    keyapp: str
    keyuser: str
    mode: str
    action: str
    type: str
    streamtype: str
    protocoltorrent: str
    idtvdb: int | None = None
    idtmdb: int | None = None
    numberseason: int | None = None
    numberepisode: int | None = None
    access: str | None = None
    debridlookup: str | None = None


class OrionoidScrapeResponse(BaseModel):
    class Data(BaseModel):
        class Stream(BaseModel):
            class File(BaseModel):
                name: str | None
                hash: str | None

            file: File

        streams: list[Stream]

    data: Data | None


class Orionoid(ScraperService[OrionoidConfig]):
    requires_imdb_id = True

    """Scraper for `Orionoid`"""

    def __init__(self):
        super().__init__("orionoid")
        self.base_url = "https://api.orionoid.com"
        self.settings = settings_manager.settings.scraping.orionoid
        self.timeout = self.settings.timeout
        self.is_premium = False
        self.is_unlimited = False
        self.initialized = False

        self.session = SmartSession(
            base_url=self.base_url,
            rate_limits=(
                {
                    # 50 calls per minute
                    "api.orionoid.com": {
                        "rate": 50 / 60,
                        "capacity": 50,
                    }
                }
                if self.settings.ratelimit
                else None
            ),
            retries=self.settings.retries,
            backoff_factor=0.3,
        )
        self._initialize()

    def validate(self) -> bool:
        """Validate the Orionoid class_settings."""

        if not self.settings.enabled:
            return False

        if len(self.settings.api_key) != 32 or self.settings.api_key == "":
            logger.error(
                "Orionoid API Key is not valid or not set. Please check your settings."
            )
            return False

        if self.timeout <= 0:
            logger.error("Orionoid timeout is not set or invalid.")
            return False

        try:
            url = f"?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
            response = self.session.get(url, timeout=self.timeout)

            if not response.ok:
                error_response = OrionoidErrorResponse.model_validate(response.json())

                logger.error(
                    f"Orionoid failed to authenticate: {error_response.result.message}"
                )

                return False

            auth_response = OrionoidAuthResponse.model_validate(response.json())

            if auth_response.result.status != "success":
                logger.error(
                    f"Orionoid API Key is invalid. Status: {auth_response.result.status}",
                )
                return False

            self.is_unlimited = auth_response.is_unlimited
            self.is_premium = auth_response.is_premium

            return True
        except Exception as e:
            logger.exception(f"Orionoid failed to initialize: {e}")
            return False

    def check_limit(self) -> bool:
        """Check if the user has exceeded the rate limit for the Orionoid API."""

        url = f"?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"

        try:
            response = self.session.get(url)

            if not response.ok:
                error_response = OrionoidErrorResponse.model_validate(response.json())

                logger.error(
                    f"Orionoid failed to check limit: {error_response.result.message}"
                )

                return False

            data = OrionoidAuthResponse.model_validate(response.json())

            if data.data:
                remaining = data.data.requests.streams.daily.remaining

                return remaining is not None and remaining <= 0
        except Exception as e:
            logger.error(f"Orionoid failed to check limit: {e}")

        return False

    def run(self, item: MediaItem) -> dict[str, str]:
        """Scrape the orionoid site for the given media items and update the object with scraped streams."""

        if not self.is_unlimited:
            limit_hit = self.check_limit()

            if limit_hit:
                logger.debug("Orionoid daily limits have been reached")
                return {}

        try:
            return self.scrape(item)
        except CircuitBreakerOpen:
            logger.debug(
                f"Circuit breaker OPEN for Orionoid; skipping {item.log_string}"
            )
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Orionoid ratelimit exceeded for item: {item.log_string}")
            else:
                logger.debug(
                    f"Orionoid exception for item: {item.log_string} - Exception: {str(e)}"
                )

        return {}

    def _build_query_params(self, item: MediaItem) -> OrionoidScrapeParams:
        """Construct the query parameters for the Orionoid API based on the media item."""

        media_type = "movie" if isinstance(item, Movie) else "show"

        raw_params: dict[str, str | int | None] = {
            "keyapp": KEY_APP,
            "keyuser": self.settings.api_key,
            "mode": "stream",
            "action": "retrieve",
            "type": media_type,
            "streamtype": "torrent",
            "protocoltorrent": "magnet",
        }

        if isinstance(item, Season):
            raw_params["numberseason"] = item.number
        elif isinstance(item, Episode):
            raw_params["numberseason"] = item.parent.number
            raw_params["numberepisode"] = item.number

        if self.settings.cached_results_only:
            raw_params["access"] = "realdebridtorrent"
            raw_params["debridlookup"] = "realdebrid"

        if isinstance(item, (Show, Season, Episode)):
            raw_params["idtvdb"] = item.tvdb_id
        elif isinstance(item, Movie):
            raw_params["idtmdb"] = item.tmdb_id

        for key, value in self.settings.parameters:
            if key not in raw_params:
                raw_params[key] = value

        return OrionoidScrapeParams.model_validate(raw_params)

    def scrape(self, item: MediaItem) -> dict[str, str]:
        """Wrapper for `Orionoid` scrape method"""

        params = self._build_query_params(item)
        response = self.session.get(
            "",
            params=params.model_dump(),
            timeout=self.timeout,
        )

        if not response.ok:
            logger.error(
                f"Orionoid scrape failed for {item.log_string}: {response.text}"
            )

            return {}

        try:
            OrionoidErrorResponse.model_validate(response.json())

            logger.error(
                f"Orionoid scrape failed for {item.log_string}: {response.text}"
            )

            return {}
        except ValidationError:
            pass

        data = OrionoidScrapeResponse.model_validate(response.json())

        if not data.data:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = dict[str, str]()

        for stream in data.data.streams:
            if not stream.file.hash or not stream.file.name:
                continue

            torrents[stream.file.hash] = stream.file.name

        if torrents:
            logger.log(
                "SCRAPER", f"Found {len(torrents)} streams for {item.log_string}"
            )
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
