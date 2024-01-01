""" Orionoid scraper module """
from typing import Optional
from pydantic import BaseModel
from requests import RequestException
from .base import Base
from utils.logger import logger
from utils.request import RateLimitExceeded, RateLimiter, get
from utils.settings import settings_manager
from utils.utils import parser


class OrionoidConfig(BaseModel):
    api_key: Optional[str]


class Orionoid(Base):
    """Scraper for Orionoid"""

    def __init__(self):
        self.settings = "orionoid"
        self.class_settings = OrionoidConfig(**settings_manager.get(self.settings))
        self.keyapp = "D3CH6HMX9KD9EMD68RXRCDUNBDJV5HRR"
        self.keyuser = self.class_settings.api_key
        self.last_scrape = 0
        self.is_premium = False
        self.initialized = False

        if self.validate_settings():
            self.is_premium = self.check_premium()
            self.initialized = True

        self.max_calls = 50 if not self.is_premium else 999999
        self.minute_limiter = RateLimiter(max_calls=self.max_calls, period=86400, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=1)

    def validate_settings(self) -> bool:
        """Validate the Orionoid class_settings."""
        if self.class_settings.api_key:
            return True
        logger.info("Orionoid is not configured and will not be used.")
        return False

    def run(self, item):
        """Scrape the torrentio site for the given media items
        and update the object with scraped streams"""
        if self._can_we_scrape(item):
            try:
                self._scrape_item(item)
            except RequestException:
                self.minute_limiter.limit_hit()
                return
            except RateLimitExceeded:
                self.minute_limiter.limit_hit()
                return

    def check_premium(self) -> bool:
        """
        Check the user's status with the Orionoid API.
        Returns True if the user is active, has a premium account, and has RealDebrid service enabled.
        """
        url = f"https://api.orionoid.com?keyapp={self.keyapp}&keyuser={self.keyuser}&mode=user&action=retrieve"
        response = get(url, retry_if_failed=False)
        if response.is_ok and response.data.data:
            active = True if response.data.data.status == "active" else False
            premium = response.data.data.subscription.package.premium
            debrid = response.data.data.service.realdebrid
            if active and premium and debrid:
                logger.info("Orionoid Premium Account Detected.")
                return True
        else:
            logger.error(f"Orionoid Free Account Detected.")
        return False

    def _scrape_item(self, item):
        """Scrape the given media item"""
        data = self.api_scrape(item)
        log_string = self._build_log_string(item)
        if len(data) > 0:
            item.set("streams", data)
            logger.debug("Found %s streams for %s", len(data), log_string)
        else:
            logger.debug("Could not find streams for %s", log_string)

    def construct_url(self, media_type, imdb_id, season = None, episode = None) -> str:
        """Construct the URL for the Orionoid API."""
        base_url = "https://api.orionoid.com"
        params = {
            "keyapp": self.keyapp,
            "keyuser": self.keyuser,
            "mode": "stream",
            "action": "retrieve",
            "type": media_type,
            "idimdb": imdb_id[2:],
            "streamtype": "torrent",
            "filename": "true",
            "limitcount": "200" if self.is_premium else "10",
            "video3d": "false",
            "sortorder": "descending",
            "sortvalue": "best" if self.is_premium else "popularity",
        }
        if media_type == "show":
            params["numberseason"] = season
            params["numberepisode"] = episode if episode else 1
        return f"{base_url}?{'&'.join([f'{key}={value}' for key, value in params.items()])}"

    def api_scrape(self, item):
        """Wrapper for Orionoid scrape method"""
        with self.minute_limiter:
            if item.type == "season":
                imdb_id = item.parent.imdb_id
                url = self.construct_url("show", imdb_id, season=item.number)
            elif item.type == "episode":
                imdb_id = item.parent.parent.imdb_id
                url = self.construct_url("show", imdb_id, season=item.parent.number, episode=item.number)
            else:
                imdb_id = item.imdb_id
                url = self.construct_url("movie", imdb_id)

            with self.second_limiter:
                response = get(url, retry_if_failed=False, timeout=30)
            if response.is_ok:
                data = {}
                for stream in response.data.data.streams:
                    title = stream.file.name
                    infoHash = stream.file.hash
                    if parser.parse(title) and infoHash:
                        data[infoHash] = {"name": title}
                if len(data) > 0:
                    return data
            return {}