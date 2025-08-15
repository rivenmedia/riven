""" Rarbg scraper module """
from typing import Dict

from loguru import logger

from program.media.item import MediaItem
from program.services.scrapers.shared import (
    ScraperRequestHandler,
    _get_stremio_identifier,
)
from program.settings.manager import settings_manager
from program.settings.models import RarbgConfig
from program.utils.request import (
    HttpMethod,
    RateLimitExceeded,
    create_service_session,
    get_rate_limit_params,
)


class Rarbg:
    """Scraper for `TheRARBG`"""

    def __init__(self):
        self.key = "therarbg"
        self.settings: RarbgConfig = settings_manager.settings.scraping.rarbg
        self.timeout: int = self.settings.timeout
        rate_limit_params = get_rate_limit_params(max_calls=1, period=5) if self.settings.ratelimit else None
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.request_handler = ScraperRequestHandler(session)
        self.initialized: bool = self.validate()
        if not self.initialized:
            return
        logger.success("TheRARBG initialized!")

    def validate(self) -> bool:
        """Validate the TheRARBG settings."""
        if not self.settings.enabled:
            return False
        if not self.settings.url:
            logger.error("TheRARBG URL is not configured and will not be used.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("TheRARBG timeout is not set or invalid.")
            return False
        try:
            url = f"{self.settings.url}/get-posts/keywords:Game%20of%20Thrones:category:Movies:category:TV:category:Anime:ncategory:XXX/?format=json"
            response = self.request_handler.execute(HttpMethod.GET, url, timeout=10)
            if response.is_ok:
                return True
        except Exception as e:
            logger.error(f"TheRARBG failed to initialize: {e}", exc_info=True)
            return False
        return True

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape TheRARBG with the given media item for streams"""
        try:
            return self.scrape(item)
        except RateLimitExceeded:
            logger.debug(f"TheRARBG rate limit exceeded for item: {item.log_string}")
        except Exception as e:
            logger.exception(f"TheRARBG exception thrown: {str(e)}")
        return {}

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Wrapper for `TheRARBG` scrape method"""
        search_string = item.log_string if item.type != "movie" else f"{item.log_string} ({item.aired_at.year})"
        url = f"{self.settings.url}/get-posts/keywords:{search_string}:category:Movies:category:TV:category:Anime:ncategory:XXX/?format=json"
        
        torrents: Dict[str, str] = {}
        current_url = url
        page = 1
        
        while current_url:
            response = self.request_handler.execute(HttpMethod.GET, current_url, timeout=self.timeout)
            if not response.is_ok or not hasattr(response, 'data'):
                break

            if hasattr(response.data, 'results'):
                for result in response.data.results:
                    if not result.h:  # h is the infoHash
                        continue

                    info_hash = result.h.lower()
                    title = result.n  # n is the title
                    torrents[info_hash] = title

            if page == 2: # 50 results per page, 100 results max
                break

            current_url = None
            if hasattr(response.data, 'links') and response.data.links and response.data.links.next:
                if (next_url := response.data.links.next):
                    current_url = next_url
                    page += 1

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents
