""" Orionoid scraper module """
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from requests.exceptions import RequestException
from utils.logger import logger, get_data_path
from utils.request import RateLimitExceeded, RateLimiter, get
from utils.settings import settings_manager
from utils.utils import parser
import time
import pickle
import os


class OrionoidConfig(BaseModel):
    api_key: Optional[str]
    movie_filter: Optional[str]
    tv_filter: Optional[str]


class Orionoid:
    """Scraper for Orionoid"""

    def __init__(self):
        self.settings = "orionoid"
        self.class_settings = OrionoidConfig(**settings_manager.get(self.settings))
        self.validate_settings()
        self.data_path = get_data_path()
        self.token_file = os.path.join(self.data_path, "orionoid_token.pkl")
        self.client_id = "GPQJBFGJKAHVFM37LJDNNLTHKJMXEAJJ"
        self.token = self.load_token()
        if not self.token:
            self.token = self.oauth()
        if self.token:
            self.is_premium = self.check_premium()
        self.scrape_limit = None  # TODO: Implement scrape limit based on user account
        max_calls = (
            50 if self.scrape_limit != "unlimited" else 2500
        )  # 50 calls a day default for free accounts.
        self.minute_limiter = RateLimiter(
            max_calls=max_calls, period=86400, raise_on_limit=True
        )
        self.second_limiter = RateLimiter(max_calls=1, period=1)
        self.initialized = self.token is not None

    def validate_settings(self):
        """Validate the Orionoid class_settings."""
        if not self.class_settings.api_key:
            logger.info("Orionoid is not configured and will not be used.")

    def oauth(self) -> Optional[str]:
        """Authenticate with Orionoid and return the token."""
        logger.info("Starting OAuth process for Orionoid.")
        url = f"https://api.orionoid.com?keyapp={self.client_id}&mode=user&action=authenticate"
        response = get(url, retry_if_failed=False)
        if response.is_ok and hasattr(response.data, "data"):
            auth_code = response.data.data.code
            direct_url = response.data.data.direct
            logger.info(f"Please authenticate using the following URL: {direct_url}")
            token_url = f"https://api.orionoid.com?keyapp={self.client_id}&mode=user&action=authenticate&code={auth_code}"
            start_time = time.time()
            timeout = 300  # 5 minutes timeout
            while time.time() - start_time < timeout:
                token_response = get(token_url, retry_if_failed=False)
                if token_response.is_ok and hasattr(token_response.data, "data"):
                    token = token_response.data.data.token
                    self.save_token(token)
                    logger.info("Authentication Token Saved.")
                    return token
                time.sleep(5)
            logger.warning("Authentication timeout. Please try again.")
        else:
            logger.warning("Failed to initiate authentication process.")
        return None

    def check_premium(self) -> bool:
        """
        Check the user's status with the Orionoid API.
        Returns True if the user is active, has a premium account, and has RealDebrid service enabled.
        """
        url = f"https://api.orionoid.com?token={self.token}&mode=user&action=retrieve"
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

    def load_token(self):
        """Load the token from a file if it exists."""
        if os.path.exists(self.token_file):
            with open(self.token_file, "rb") as file:
                return pickle.load(file)
        return None

    def save_token(self, token: str):
        """Save the token to a file for later use."""
        with open(self.token_file, "wb") as file:
            pickle.dump(token, file)

    def run(self, item):
        """Scrape the Orionoid site for the given media items
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

    def _scrape_item(self, item):
        """Scrape the Orionoid site for the given media item and log the results."""
        data = self.api_scrape(item)
        log_string = item.title
        if item.type == "season":
            log_string = f"{item.parent.title} S{item.number}"
        if item.type == "episode":
            log_string = (
                f"{item.parent.parent.title} S{item.parent.number}E{item.number}"
            )
        if len(data) > 0:
            item.set("streams", data)
            logger.debug("Found %s streams for %s", len(data), log_string)
        else:
            logger.debug("Could not find streams for %s", log_string)

    def construct_url(self, media_type, imdb_id, season=None, episode=1) -> str:
        """Construct the URL for the Orionoid API."""
        base_url = "https://api.orionoid.com"
        params = {
            "token": self.token,
            "mode": "stream",
            "action": "retrieve",
            "type": media_type,
            "idimdb": imdb_id[2:],
            "protocoltorrent": "magnet",
            "access": "realdebrid",
            "debridlookup": "realdebrid",
            "filename": "true",
            "fileunknown": "false",
            "limitcount": "10",
            "video3d": "false",
            "videoquality": "sd,hd720,hd1080,hd2k,hd4k",
            "sortorder": "descending",
            "sortvalue": "best" if self.is_premium else "popularity",
            "metarelease": "bdrip,bdrmx,bluray,webdl,ppv,dvdrip",
        }

        if media_type == "show":
            params["numberseason"] = season if season is not None else "1"
            params["numberepisode"] = str(episode)

        custom_filters = (
            self.class_settings.movie_filter
            if media_type == "movie"
            else self.class_settings.tv_filter
        )
        custom_filters = custom_filters.lstrip("&") if custom_filters else ""
        url = f"{base_url}?{'&'.join([f'{key}={value}' for key, value in params.items()])}"
        if custom_filters:
            url += f"&{custom_filters}"
        return url

    def _can_we_scrape(self, item) -> bool:
        return self._is_released(item) and self._needs_new_scrape(item)

    def _needs_new_scrape(self, item) -> bool:
        """Determine if a new scrape is needed based on the last scrape time."""
        current_time = datetime.now().timestamp()
        scrape_interval = (
            60 * 60 if self.is_premium else 60 * 60 * 24
        )  # 1 hour for premium, 1 day for non-premium
        return current_time - item.scraped_at > scrape_interval or item.scraped_at == 0

    def api_scrape(self, item):
        """Wrapper for Orionoid scrape method"""
        with self.minute_limiter:
            if item.type == "season":
                imdb_id = item.parent.imdb_id
                url = self.construct_url("show", imdb_id, season=item.number)
            elif item.type == "episode":
                imdb_id = item.parent.parent.imdb_id
                url = self.construct_url(
                    "show", imdb_id, season=item.parent.number, episode=item.number or 1
                )
            else:  # item.type == "movie"
                imdb_id = item.imdb_id
                url = self.construct_url("movie", imdb_id)

            with self.second_limiter:
                response = self.get(url, retry_if_failed=False, timeout=60)
                item.set("scraped_at", datetime.now().timestamp())
            if response.is_ok:
                data = {}
                for stream in response.data.data.streams:
                    title = stream.file.name
                    infoHash = stream.file.hash
                    if parser.parse(title) and infoHash:
                        data[infoHash] = {
                            "name": title,
                        }
                if len(data) > 0:
                    return data
            return {}
