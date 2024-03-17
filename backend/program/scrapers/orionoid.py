""" Orionoid scraper module """
from datetime import datetime

from program.media.item import Episode, Season, Show
from program.settings.manager import settings_manager
from program.versions.parser import ParsedTorrents, Torrent
from requests import ConnectTimeout
from requests.exceptions import RequestException
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get

KEY_APP = "D3CH6HMX9KD9EMD68RXRCDUNBDJV5HRR"


class Orionoid:
    """Scraper for `Orionoid`"""

    def __init__(self):
        self.key = "orionoid"
        self.settings = settings_manager.settings.scraping.orionoid
        self.is_premium = False
        self.is_unlimited = False
        self.initialized = False
        if self.validate():
            self.is_premium = self.check_premium()
            self.initialized = True
        else:
            return
        self.orionoid_limit = 0
        self.orionoid_expiration = datetime.now()
        self.parse_logging = False
        self.max_calls = 100 if not self.is_premium else 1000
        self.period = 86400 if not self.is_premium else 3600
        self.minute_limiter = RateLimiter(
            max_calls=self.max_calls, period=self.period, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        logger.info("Orionoid initialized!")

    def validate(self) -> bool:
        """Validate the Orionoid class_settings."""
        if not self.settings.enabled:
            logger.debug("Orionoid is set to disabled.")
            return False
        if len(self.settings.api_key) != 32 or self.settings.api_key == "":
            logger.error(
                "Orionoid API Key is not valid or not set. Please check your settings."
            )
            return False
        try:
            url = f"https://api.orionoid.com?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
            response = get(url, retry_if_failed=False)
            if response.is_ok and hasattr(response.data, "result"):
                if response.data.result.status != "success":
                    logger.error(
                        "Orionoid API Key is invalid. Status: %s",
                        response.data.result.status,
                    )
                    return False
                if not response.is_ok:
                    logger.error(
                        "Orionoid Status Code: %s, Reason: %s",
                        response.status_code,
                        response.data.reason,
                    )
                    return False
                if response.data.data.subscription.package.type == "unlimited":
                    self.is_unlimited = True
            return True
        except Exception as e:
            logger.exception("Orionoid failed to initialize: %s", e)
            return False

    def check_premium(self) -> bool:
        """Check if the user is active, has a premium account, and has RealDebrid service enabled."""
        url = f"https://api.orionoid.com?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
        response = get(url, retry_if_failed=False)
        if response.is_ok and hasattr(response.data, "data"):
            active = response.data.data.status == "active"
            premium = response.data.data.subscription.package.premium
            debrid = response.data.data.service.realdebrid
            if active and premium and debrid:
                logger.info("Orionoid Premium Account Detected.")
                return True
            else:
                logger.error("Orionoid Free Account Detected.")
        return False

    def run(self, item):
        """Scrape the orionoid site for the given media items
        and update the object with scraped streams"""
        if item is None or isinstance(item, Show):
            yield item
        try:
            yield self._scrape_item(item)
        except ConnectTimeout:
            self.minute_limiter.limit_hit()
            logger.warn("Orionoid connection timeout for item: %s", item.log_string)
        except RequestException as e:
            self.minute_limiter.limit_hit()
            logger.exception("Orionoid request exception: %s", e)
        except RateLimitExceeded:
            self.minute_limiter.limit_hit()
            logger.warn("Orionoid rate limit hit for item: %s", item.log_string)
        except Exception as e:
            self.minute_limiter.limit_hit()
            logger.exception(
                "Orionoid exception for item: %s - Exception: %s", item.log_string, e
            )
        return item

    def _scrape_item(self, item):
        """Scrape the given media item"""
        data, stream_count = self.api_scrape(item)
        if len(data) > 0:
            item.streams.update(data.torrents)
            logger.debug(
                "Found %s streams out of %s for %s",
                len(data),
                stream_count,
                item.log_string,
            )
        elif stream_count > 0:
            logger.debug(
                "Could not find good streams for %s out of %s",
                item.log_string,
                stream_count,
            )
        else:
            logger.debug("No streams found for %s", item.log_string)
        return item

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
            "limitcount": self.settings.limitcount if self.settings.limitcount else 5,
            "video3d": "false",
            "sortorder": "descending",
            "sortvalue": "best" if self.is_premium else "popularity",
        }

        if self.is_unlimited:
            # This can use 2x towards your Orionoid limits. Only use if user is unlimited.
            params["debridlookup"] = "realdebrid"

         # There are 200 results per page. We probably don't need to go over 200.
        if self.settings.limitcount > 200:
            params["limitcount"] = 200

        if media_type == "show":
            params["numberseason"] = season
            params["numberepisode"] = episode if episode else 1

        return f"{base_url}?{'&'.join([f'{key}={value}' for key, value in params.items()])}"

    def api_scrape(self, item) -> tuple[ParsedTorrents, int]:
        """Wrapper for `Orionoid` scrape method"""
        with self.minute_limiter:
            if isinstance(item, Season):
                imdb_id = item.parent.imdb_id
                url = self.construct_url("show", imdb_id, season=item.number)
            elif isinstance(item, Episode):
                imdb_id = item.parent.parent.imdb_id
                url = self.construct_url(
                    "show", imdb_id, season=item.parent.number, episode=item.number
                )
            else:
                imdb_id = item.imdb_id
                url = self.construct_url("movie", imdb_id)

            with self.second_limiter:
                response = get(url, retry_if_failed=False, timeout=60)
            if not response.is_ok or not hasattr(response.data, "data"):
                return {}, 0
            scraped_torrents = ParsedTorrents()
            for stream in response.data.data.streams:
                if not stream.file.hash:
                    continue
                torrent: Torrent = Torrent(
                    item=item,
                    raw_title=stream.file.name,
                    infohash=stream.file.hash
                    )
                if torrent and torrent.parsed_data.fetch:
                    scraped_torrents.add(torrent)
            return scraped_torrents, len(response.data.data.streams)
