""" Orionoid scraper module """
from datetime import datetime
from typing import Dict

from program.media.item import Episode, MediaItem, Season, Show
from program.settings.manager import settings_manager
from program.settings.versions import models
from requests import ConnectTimeout, ReadTimeout
from requests.exceptions import RequestException
from RTN import RTN, Torrent, sort_torrents
from RTN.exceptions import GarbageTorrent
from utils.logger import logger
from utils.request import RateLimiter, RateLimitExceeded, get

KEY_APP = "D3CH6HMX9KD9EMD68RXRCDUNBDJV5HRR"


class Orionoid:
    """Scraper for `Orionoid`"""

    def __init__(self, hash_cache):
        self.key = "orionoid"
        self.settings = settings_manager.settings.scraping.orionoid
        self.settings_model = settings_manager.settings.ranking
        self.ranking_model = models.get(self.settings_model.profile)
        self.timeout = self.settings.timeout
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
        self.second_limiter = RateLimiter(max_calls=1, period=5) if self.settings.ratelimit else None
        self.rtn = RTN(self.settings_model, self.ranking_model)
        self.hash_cache = hash_cache
        logger.success("Orionoid initialized!")

    def validate(self) -> bool:
        """Validate the Orionoid class_settings."""
        if not self.settings.enabled:
            logger.warning("Orionoid is set to disabled.")
            return False
        if len(self.settings.api_key) != 32 or self.settings.api_key == "":
            logger.error("Orionoid API Key is not valid or not set. Please check your settings.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Orionoid timeout is not set or invalid.")
            return False
        if not isinstance(self.settings.ratelimit, bool):
            logger.error("Orionoid ratelimit must be a valid boolean.")
            return False
        try:
            url = f"https://api.orionoid.com?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
            response = get(url, retry_if_failed=True, timeout=self.timeout)
            if response.is_ok and hasattr(response.data, "result"):
                if response.data.result.status != "success":
                    logger.error(
                        f"Orionoid API Key is invalid. Status: {response.data.result.status}",
                    )
                    return False
                if not response.is_ok:
                    logger.error(
                        f"Orionoid Status Code: {response.status_code}, Reason: {response.data.reason}",
                    )
                    return False
                if response.data.data.subscription.package.type == "unlimited":
                    self.is_unlimited = True
            return True
        except Exception as e:
            logger.exception(f"Orionoid failed to initialize: {e}")
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
                logger.warning("Orionoid Free Account Detected.")
        return False

    def run(self, item: MediaItem):
        """Scrape the orionoid site for the given media items and update the object with scraped streams."""
        if not item or isinstance(item, Show):
            yield item
            return

        try:
            yield self.scrape(item)
        except RateLimitExceeded:
            if self.second_limiter:
                self.second_limiter.limit_hit()
            else:
                logger.warning(f"Orionoid rate limit exceeded for item: {item.log_string}")
        except ConnectTimeout:
            logger.warning(f"Orionoid connection timeout for item: {item.log_string}")
        except ReadTimeout:
            logger.error(f"Orionoid read timeout for item: {item.log_string}")
        except RequestException as e:
            logger.error(f"Orionoid request exception: {e}")
        except Exception as e:
            logger.error(f"Orionoid exception for item: {item.log_string} - Exception: {e}")
        yield item

    def scrape(self, item: MediaItem) -> MediaItem:
        """Scrape the given media item"""
        try:
            data, stream_count = self.api_scrape(item)
        except Exception as e:
            raise e  # Raise the exception to be handled by the run method

        if len(data) > 0:
            item.streams.update(data)
            logger.log("SCRAPER", f"Found {len(data)} streams out of {stream_count} for {item.log_string}")
        elif stream_count > 0:
            logger.log("NOT_FOUND", f"Could not find good streams for {item.log_string} out of {stream_count}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
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

    def api_scrape(self, item: MediaItem) -> tuple[Dict, int]:
        """Wrapper for `Orionoid` scrape method"""
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

        if self.second_limiter:
            with self.second_limiter:
                response = get(url, timeout=self.timeout)
        else:
            response = get(url, timeout=self.timeout)

        if not response.is_ok or not hasattr(response.data, "data"):
            return {}, 0

        torrents = set()
        correct_title = item.get_top_title()

        if not correct_title:
            logger.log("SCRAPER", f"Correct title not found for {item.log_string}")
            return {}, 0

        for stream in response.data.data.streams:
            if (
                not stream.file.hash or 
                not stream.file.name or 
                self.hash_cache.is_blacklisted(stream.file.hash)
            ):
                continue
            try:
                torrent: Torrent = self.rtn.rank(
                    raw_title=stream.file.name,
                    infohash=stream.file.hash,
                    correct_title=correct_title,
                    remove_trash=True
                )
            except GarbageTorrent:
                continue

            if torrent and torrent.fetch:
                torrents.add(torrent)

        scraped_torrents = sort_torrents(torrents)
        return scraped_torrents, len(response.data.data.streams)
