""" Orionoid scraper module """
from typing import Dict

from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.utils.request import SmartSession

KEY_APP = "D3CH6HMX9KD9EMD68RXRCDUNBDJV5HRR"


class Orionoid:
    """Scraper for `Orionoid`"""

    def __init__(self):
        self.key = "orionoid"
        self.base_url = "https://api.orionoid.com"
        self.settings = settings_manager.settings.scraping.orionoid
        self.timeout = self.settings.timeout
        self.is_premium = False
        self.is_unlimited = False
        self.initialized = False

        if self.settings.ratelimit:
            rate_limits = {
                "api.orionoid.com": {"rate": 50/60, "capacity": 50}  # 50 calls per minute
            }
        else:
            rate_limits = {}
        
        self.session = SmartSession(
            base_url=self.base_url,
            rate_limits=rate_limits,
            retries=3,
            backoff_factor=0.3
        )
        
        if self.validate():
            self.is_premium = self.check_premium()
            self.initialized = True
        else:
            return
        logger.success("Orionoid initialized!")

    def validate(self) -> bool:
        """Validate the Orionoid class_settings."""
        if not self.settings.enabled:
            return False
        if len(self.settings.api_key) != 32 or self.settings.api_key == "":
            logger.error("Orionoid API Key is not valid or not set. Please check your settings.")
            return False
        if not isinstance(self.timeout, int) or self.timeout <= 0:
            logger.error("Orionoid timeout is not set or invalid.")
            return False
        try:
            url = f"?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
            response = self.session.get(url, timeout=self.timeout)
            if response.ok and hasattr(response.data, "result"):
                if response.data.result.status != "success":
                    logger.error(
                        f"Orionoid API Key is invalid. Status: {response.data.result.status}",
                    )
                    return False
                if not response.ok:
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
        url = f"?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
        response = self.session.get(url)
        if response.ok and hasattr(response.data, "data"):
            active = response.data.data.status == "active"
            premium = response.data.data.subscription.package.premium
            debrid = response.data.data.service.realdebrid
            if active and premium and debrid:
                return True
        return False

    def check_limit(self) -> bool:
        """Check if the user has exceeded the rate limit for the Orionoid API."""
        url = f"?keyapp={KEY_APP}&keyuser={self.settings.api_key}&mode=user&action=retrieve"
        try:
            response = self.session.get(url)
            if response.ok and hasattr(response.data, "data"):
                remaining = response.data.data.requests.streams.daily.remaining
                if remaining is None:
                    return False
                elif remaining and remaining <= 0:
                    return True
        except Exception as e:
            logger.error(f"Orionoid failed to check limit: {e}")
            return False

    def run(self, item: MediaItem) -> Dict[str, str]:
        """Scrape the orionoid site for the given media items and update the object with scraped streams."""
        if not item:
            return {}

        if not self.is_unlimited:
            limit_hit = self.check_limit()
            if limit_hit:
                logger.debug("Orionoid daily limits have been reached")
                return {}

        try:
            return self.scrape(item)
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                logger.debug(f"Orionoid ratelimit exceeded for item: {item.log_string}")
            else:
                logger.exception(f"Orionoid exception for item: {item.log_string} - Exception: {e}")
        return {}

    def _build_query_params(self, item: MediaItem) -> dict:
        """Construct the query parameters for the Orionoid API based on the media item."""
        media_type = "movie" if item.type == "movie" else "show"
        imdbid: str = item.get_top_imdb_id()
        if not imdbid:
            raise ValueError("IMDB ID is missing for the media item")

        params = {
            "keyapp": KEY_APP,
            "keyuser": self.settings.api_key,
            "mode": "stream",
            "action": "retrieve",
            "type": media_type,
            "idimdb": imdbid[2:],
            "streamtype": "torrent",
            "protocoltorrent": "magnet"
        }

        if item.type == "season":
            params["numberseason"] = item.number
        elif item.type == "episode":
            params["numberseason"] = item.parent.number
            params["numberepisode"] = item.number

        if self.settings.cached_results_only:
            params["access"] = "realdebridtorrent"
            params["debridlookup"] = "realdebrid"

        for key, value in self.settings.parameters.items():
            if key not in params:
                params[key] = value

        return params

    def scrape(self, item: MediaItem) -> Dict[str, str]:
        """Wrapper for `Orionoid` scrape method"""
        params = self._build_query_params(item)
        response = self.session.get("", params=params, timeout=self.timeout)
        if not response.ok or not hasattr(response.data, "data"):
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")
            return {}

        torrents = {}
        for stream in response.data.data.streams:
            if not stream.file.hash or not stream.file.name:
                continue
            torrents[stream.file.hash] = stream.file.name

        if torrents:
            logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        else:
            logger.log("NOT_FOUND", f"No streams found for {item.log_string}")

        return torrents