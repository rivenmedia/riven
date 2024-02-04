""" Orionoid scraper module """
from typing import Optional

from requests import ConnectTimeout
from requests.exceptions import RequestException

from utils.logger import logger
from utils.request import RateLimitExceeded, RateLimiter, get
from program.settings.manager import settings_manager
from utils.parser import parser

KEY_APP = "D3CH6HMX9KD9EMD68RXRCDUNBDJV5HRR"


class Orionoid:
    """Scraper for `Orionoid`"""

    def __init__(self, _):
        self.key = "orionoid"
        self.settings = settings_manager.settings.scraper.orionoid
        self.is_premium = False
        self.initialized = False
        if self.validate_settings():
            self.is_premium = self.check_premium()
            self.initialized = True
        else:
            return
        self.orionoid_limit = 0
        self.orionoid_remaining = 0
        self.parse_logging = False
        self.max_calls = 100 if not self.is_premium else 1000
        self.period = 86400 if not self.is_premium else 3600
        self.minute_limiter = RateLimiter(max_calls=self.max_calls, period=self.period, raise_on_limit=True)
        self.second_limiter = RateLimiter(max_calls=1, period=5)
        logger.info("Orionoid initialized!")

    def validate_settings(self) -> bool:
        """Validate the Orionoid class_settings."""
        if not self.settings.enabled:
            logger.debug("Orionoid is set to disabled.")
            return False
        if len(self.settings.api_key) != 32 or self.settings.api_key == "":
            logger.error("Orionoid API Key is not valid or not set. Please check your settings.")
            return False
        try:
            url = f"https://api.orionoid.com?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
            response = get(url, retry_if_failed=False)
            if response.is_ok and hasattr(response.data, "result"):
                if not response.data.result.status == "success":
                    logger.error(f"Orionoid API Key is invalid. Status: {response.data.result.status}")
                    return False
                if not response.is_ok:
                    logger.error(f"Orionoid Status Code: {response.status_code}, Reason: {response.reason}")
                    return False
            return True
        except Exception as e:
            logger.exception("Orionoid failed to initialize: %s", e)
            return False

    def check_premium(self) -> bool:
        """
        Check the user's status with the Orionoid API.
        Returns True if the user is active, has a premium account, and has RealDebrid service enabled.
        """
        url = f"https://api.orionoid.com?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
        response = get(url, retry_if_failed=False)
        if response.is_ok and hasattr(response.data, "data"):
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
        if item is None or not self.initialized:
            return
        try:
            self._scrape_item(item)
        except ConnectTimeout:
            self.minute_limiter.limit_hit()
            logger.warn("Orionoid connection timeout for item: %s", item.log_string)
            return
        except RequestException as e:
            self.minute_limiter.limit_hit()
            logger.exception("Orionoid request exception: %s", e)
            return
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
            logger.warn("Orionoid rate limit hit for item: %s", item.log_string)
            return
        except Exception as e:
            self.minute_limiter.limit_hit()
            logger.exception("Orionoid exception for item: %s - Exception: %s", item.log_string, e)
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
            if response.is_ok and hasattr(response.data, "data"):

                # Check and log Orionoid API limits
                # self.orionoid_limit = response.data.data.requests.daily.limit
                # self.orionoid_remaining = response.data.data.requests.daily.remaining
                # if self.orionoid_remaining < 10:
                #     logger.warning(f"Orionoid API limit is low. Limit: {self.orionoid_limit}, Remaining: {self.orionoid_remaining}")

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
                if self.parse_logging:
                    for parsed_data in parsed_data_list:
                        logger.debug("Orionoid Fetch: %s - Parsed item: %s", parsed_data["fetch"], parsed_data["string"])
                if data:
                    item.parsed_data.extend(parsed_data_list)
                    return data, len(response.data.data.streams)
            return {}, 0