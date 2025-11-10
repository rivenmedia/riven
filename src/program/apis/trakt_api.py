from dataclasses import dataclass
import os
import re

from urllib.parse import urlencode

from loguru import logger
from requests import RequestException

from program.settings.manager import settings_manager
from program.settings.models import TraktModel
from program.utils.request import SmartSession


class TraktAPIError(Exception):
    """Base exception for TraktApi related errors"""


class TraktAPI:
    """Handles Trakt API communication"""

    BASE_URL = "https://api.trakt.tv"
    CLIENT_ID = os.environ.get(
        "TRAKT_API_CLIENT_ID",
        "0183a05ad97098d87287fe46da4ae286f434f32e8e951caad4cc147c947d79a3",
    )

    patterns: dict[str, re.Pattern] = {
        "user_list": re.compile(r"https://trakt.tv/users/([^/]+)/lists/([^/]+)"),
        "short_list": re.compile(r"https://trakt.tv/lists/\d+"),
    }

    def __init__(self, settings: TraktModel):
        self.settings = settings
        self.oauth_client_id = self.settings.oauth.oauth_client_id
        self.oauth_client_secret = self.settings.oauth.oauth_client_secret
        self.oauth_redirect_uri = self.settings.oauth.oauth_redirect_uri

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits={
                # 1000 calls per 5 minutes
                "api.trakt.tv": {
                    "rate": 1000 // 300,
                    "capacity": 1000,
                }
            },
            retries=2,
            backoff_factor=0.3,
        )

        self.headers = {
            "Content-type": "application/json",
            "trakt-api-key": self.CLIENT_ID,
            "trakt-api-version": "2",
        }
        self.session.headers.update(self.headers)

        if self.settings.proxy_url:
            proxies = {
                "http": self.settings.proxy_url,
                "https": self.settings.proxy_url,
            }
            self.session.proxies.update(proxies)

    def validate(self):
        return self.session.get("lists/2")

    def _fetch_data(self, url, params):
        """Fetch paginated data from Trakt API with rate limiting."""

        all_data = []
        page = 1

        while True:
            try:
                response = self.session.get(url, params={**params, "page": page})

                if response.ok:
                    data = (
                        response.data
                        if isinstance(response.data, list)
                        else [response.data]
                    )

                    if not data:
                        break

                    all_data.extend(data)

                    if "X-Pagination-Page-Count" not in response.headers:
                        break

                    if params.get("limit") and len(all_data) >= params["limit"]:
                        all_data = all_data[: params["limit"]]

                        break

                    page += 1
                elif response.status_code == 429:
                    logger.warning(
                        "Rate limit exceeded. Retrying after rate limit period."
                    )

                    break
                else:
                    logger.error(f"Failed to fetch data: {response.status_code}")

                    break
            except Exception as e:
                logger.error(f"Error fetching data: {str(e)}")

                break

        return all_data

    def get_watchlist_items(self, user):
        """Get watchlist items from Trakt with pagination support."""

        url = f"{self.BASE_URL}/users/{user}/watchlist"

        return self._fetch_data(url, {})

    def get_user_list(self, user, list_name):
        """Get user list items from Trakt with pagination support."""

        url = f"{self.BASE_URL}/users/{user}/lists/{list_name}/items"

        return self._fetch_data(url, {})

    def get_collection_items(self, user, media_type):
        """Get collections from Trakt with pagination support."""

        url = f"{self.BASE_URL}/users/{user}/collection/{media_type}"

        return self._fetch_data(url, {})

    def get_trending_items(self, media_type, limit=10):
        """Get trending items from Trakt with pagination support."""

        url = f"{self.BASE_URL}/{media_type}/trending"

        return self._fetch_data(url, {"limit": limit})

    def get_popular_items(self, media_type, limit=10):
        """Get popular items from Trakt with pagination support."""

        url = f"{self.BASE_URL}/{media_type}/popular"

        return self._fetch_data(url, {"limit": limit})

    def get_most_watched_items(self, media_type, period="weekly", limit=10):
        """Get popular items from Trakt with pagination support."""

        url = f"{self.BASE_URL}/{media_type}/watched/{period}"

        return self._fetch_data(url, {"limit": limit})

    def extract_user_list_from_url(self, url) -> tuple:
        """Extract user and list name from Trakt URL"""

        def match_full_url(url: str) -> tuple[str, ...] | tuple[None, None]:
            """Helper function to match full URL format"""

            match = self.patterns["user_list"].match(url)

            if match:
                return match.groups()

            return None, None

        # First try to match the original URL
        user, list_name = match_full_url(url)

        if user and list_name:
            return user, list_name

        # If it's a short URL, resolve it and try to match again
        match = self.patterns["short_list"].match(url)

        if match:
            full_url = self.resolve_short_url(url)
            if full_url:
                user, list_name = match_full_url(full_url)
                if user and list_name:
                    return user, list_name

        return None, None

    def get_aliases(self, imdb_id: str, item_type: str) -> dict[str, list[str]]:
        """
        Wrapper for trakt.tv API show method.

        Returns:
            dict[str, list[str]]: A dictionary where keys are country codes and values are lists of alias names.

        Ex:
        {
            "us": ["Alias 1", "Alias 2"],
            "jp": ["エイリアス1", "エイリアス2"]
        }
        """

        if not imdb_id:
            return {}

        url = f"{self.BASE_URL}/{item_type}/{imdb_id}/aliases"

        try:
            response = self.session.get(url, timeout=30)

            if response.ok and response.data:
                aliases = {}

                @dataclass
                class ResponseData:
                    @dataclass
                    class Alias:
                        country: str
                        title: str

                    data: list[Alias]

                response_data = ResponseData(data=response.json()).data

                for ns in response_data:
                    country = ns.country
                    title = ns.title

                    if title and title.startswith("Anime-"):
                        title = title[len("Anime-") :]

                    if country not in aliases:
                        aliases[country] = []

                    if title not in aliases[country]:
                        aliases[country].append(title)

                return aliases
        except Exception:
            logger.debug(f"Failed to get aliases for {imdb_id} with type {item_type}")

        return {}

    def resolve_short_url(self, short_url: str) -> str | None:
        """Resolve short URL to full URL"""

        try:
            response = self.session.get(
                url=short_url,
                headers={"Content-Type": "application/json", "Accept": "text/html"},
            )

            if response.ok:
                return response.url
            else:
                logger.error(
                    f"Failed to resolve short URL: {short_url} (with status code: {response.status_code})"
                )

                return None

        except RequestException as e:
            logger.error(f"Error resolving short URL: {str(e)}")

            return None

    def perform_oauth_flow(self) -> str:
        """Initiate the OAuth flow and return the authorization URL."""

        if (
            not self.oauth_client_id
            or not self.oauth_client_secret
            or not self.oauth_redirect_uri
        ):
            logger.error("OAuth settings not found in Trakt settings")
            raise TraktAPIError("OAuth settings not found in Trakt settings")

        params = {
            "response_type": "code",
            "client_id": self.oauth_client_id,
            "redirect_uri": self.oauth_redirect_uri,
        }
        return f"{self.BASE_URL}/oauth/authorize?{urlencode(params)}"

    def handle_oauth_callback(self, api_key: str, code: str) -> bool:
        """Handle the OAuth callback and exchange the code for an access token."""

        if (
            not self.oauth_client_id
            or not self.oauth_client_secret
            or not self.oauth_redirect_uri
        ):
            logger.error("OAuth settings not found in Trakt settings")
            return False

        token_url = f"{self.BASE_URL}/oauth/token"
        payload = {
            "code": code,
            "client_id": self.oauth_client_id,
            "client_secret": self.oauth_client_secret,
            "redirect_uri": self.oauth_redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = self.headers.copy()
        headers["trakt-api-key"] = api_key
        response = self.session.post(token_url, data=payload, headers=headers)
        if response.ok:
            token_data = response.data
            self.settings.access_token = token_data.get("access_token")
            self.settings.refresh_token = token_data.get("refresh_token")
            settings_manager.save()  # Save the tokens to settings
            return True
        else:
            logger.error(f"Failed to obtain OAuth token: {response.status_code}")
            return False
