""" Orionoid scraper module """
from typing import Optional
from pydantic import BaseModel
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimitExceeded, RateLimiter, get
from utils.settings import settings_manager
from utils.parser import parser

KEY_APP = "D3CH6HMX9KD9EMD68RXRCDUNBDJV5HRR"


class OrionoidConfig(BaseModel):
    enabled: bool
    api_key: Optional[str]


class Orionoid:
    """Scraper for `Orionoid`"""

    def __init__(self, _):
        self.key = "orionoid"
        self.settings = OrionoidConfig(**settings_manager.get(f"scraping.{self.key}"))
        self.is_premium = False
        self.initialized = False
        if self.validate_settings():
            self.is_premium = self.check_premium()
            self.initialized = True
        else:
            return
        self.max_calls = 50 if not self.is_premium else 60
        self.period = 86400 if not self.is_premium else 60
        self.minute_limiter = RateLimiter(max_calls=self.max_calls, period=self.period, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=5)
        logger.info("Orionoid initialized!")

    def validate_settings(self) -> bool:
        """Validate the Orionoid class_settings."""
        if not self.settings.enabled:
            logger.debug("Orionoid is set to disabled.")
            return False
        if self.settings.api_key:
            return True
        logger.info("Orionoid is not configured and will not be used.")
        return False

    def check_premium(self) -> bool:
        """
        Check the user's status with the Orionoid API.
        Returns True if the user is active, has a premium account, and has RealDebrid service enabled.
        """
        url = f"https://api.orionoid.com?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
        response = get(url, retry_if_failed=False)
        if response.is_ok:
            active = True if response.data.data.status == "active" else False
            premium = response.data.data.subscription.package.premium
            debrid = response.data.data.service.realdebrid
            if active and premium and debrid:
                logger.info("Orionoid Premium Account Detected.")
                return True
        else:
            logger.error(f"Orionoid Free Account Detected.")
        return False

    def run(self, item):
        """Scrape the Orionoid site for the given media items
        and update the object with scraped streams"""
        try:
            self._scrape_item(item)
        except RequestException:
            self.minute_limiter.limit_hit()
            return
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
            return

    def _scrape_item(self, item):
        data, stream_count = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data)
            logger.info("Found %s streams out of %s for %s", len(data), stream_count, item.log_string)
        else:
            logger.debug("Could not find streams for %s", item.log_string)

    def construct_url(self, media_type, imdb_id, season=None, episode=None) -> str:
        """Construct the URL for the Orionoid API."""
        base_url = "https://api.orionoid.com"
        params = {
            "keyapp": KEY_APP,
            "keyuser": self.settings.api_key,
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
                url = self.construct_url(
                    "show", imdb_id, season=item.parent.number, episode=item.number
                )
            else:
                imdb_id = item.imdb_id
                url = self.construct_url("movie", imdb_id)

            with self.second_limiter:
                response = get(url, retry_if_failed=False, timeout=60)
            if response.is_ok and len(response.data.data.streams) > 0:
                parsed_data_list = [
                    parser.parse(item, stream.file.name)
                    for stream in response.data.data.streams
                    if stream.file.hash
                ]
                data = {
                    stream.file.hash: {"name": stream.file.name}
                    for stream, parsed_data in zip(response.data.data.streams, parsed_data_list)
                    if parsed_data["fetch"]
                }
                # for parsed_data in parsed_data_list:
                #     logger.debug("Orionoid Fetch: %s - Parsed item: %s", parsed_data["fetch"], parsed_data["string"])
                if data:
                    item.parsed_data.extend(parsed_data_list)
                    item.parsed_data.append({self.key: True})
                    return data, len(response.data.data.streams)
            return {}, len(response.data.data.streams) or 0