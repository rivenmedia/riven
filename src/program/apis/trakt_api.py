import os
import re

from collections.abc import Callable
from typing import Any, Generic, Literal, TypeVar
from urllib.parse import urlencode

from loguru import logger
from pydantic import BaseModel
from requests import RequestException

from program.settings.manager import settings_manager
from program.settings.models import TraktModel
from program.utils.request import SmartSession
from schemas.trakt import GetMovies200ResponseInnerMovie, GetShows200ResponseInnerShow

MediaType = Literal["movies", "shows"]


class Watchlist(BaseModel):
    movie: GetMovies200ResponseInnerMovie | None
    show: GetShows200ResponseInnerShow | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Watchlist | None":
        try:
            return cls.model_validate(data)
        except Exception:
            return None


class PaginationParams(BaseModel):
    page: int | None = None
    limit: int | None = None


class TraktAPIError(Exception):
    """Base exception for TraktApi related errors"""


DataModel = TypeVar("DataModel", bound=BaseModel)


class PageResponse(BaseModel, Generic[DataModel]):
    data: list[DataModel]


class PaginatedResponse(PageResponse[DataModel]):
    has_next_page: bool


class TraktAPI:
    """Handles Trakt API communication"""

    BASE_URL = "https://api.trakt.tv"
    CLIENT_ID = os.environ.get(
        "TRAKT_API_CLIENT_ID",
        "0183a05ad97098d87287fe46da4ae286f434f32e8e951caad4cc147c947d79a3",
    )

    patterns = {
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
        response = self.session.get("lists/2")

        from schemas.trakt import GetList200Response

        GetList200Response.model_validate(response.json())

        return True

    def _fetch_data(
        self,
        url: str,
        model_validator: Callable[[dict[str, Any]], DataModel | None],
        *,
        limit: int | None = None,
    ) -> list[DataModel]:
        """Fetch paginated data from Trakt API with rate limiting."""

        all_data: list[DataModel] = []

        def _request_page(requested_page: int):
            response = self.session.get(
                url,
                params={
                    "limit": limit,
                    "page": requested_page,
                },
            )

            if response.ok:
                data = (
                    response.json()
                    if isinstance(response.json(), list)
                    else [response.json()]
                )

                pagination_page_header = response.headers.get("X-Pagination-Page")
                pagination_page_count_header = response.headers.get(
                    "X-Pagination-Page-Count"
                )

                assert pagination_page_count_header
                assert pagination_page_header

                pagination_page_count = int(pagination_page_count_header)
                pagination_page = int(pagination_page_header)

                has_next_page = pagination_page < pagination_page_count

                validated_data = [
                    validated_item
                    for item in data
                    if (validated_item := model_validator(item))
                ]

                return PaginatedResponse(
                    data=validated_data,
                    has_next_page=has_next_page,
                )
            elif response.status_code == 429:
                logger.warning("Rate limit exceeded. Retrying after rate limit period.")

                return None
            else:
                logger.error(f"Failed to fetch data: {response.status_code}")

                return None

        page = 1

        while True:
            try:
                page_response = _request_page(page)

                if page_response is None:
                    break

                all_data.extend(page_response.data)

                if limit and len(all_data) >= limit:
                    all_data = all_data[:limit]

                    break

                if not page_response.has_next_page:
                    break
            except Exception as e:
                logger.error(f"Error fetching data: {str(e)}")

                break

        return all_data

    def get_watchlist_items(self, user: str) -> list[Watchlist]:
        """Get watchlist items from Trakt with pagination support."""

        return self._fetch_data(
            url=f"{self.BASE_URL}/users/{user}/watchlist",
            model_validator=Watchlist.from_dict,
        )

    def get_user_list(self, user: str, list_name: str):
        """Get user list items from Trakt with pagination support."""

        from schemas.trakt import GetItemsOnAPersonalList200ResponseInner

        return self._fetch_data(
            url=f"{self.BASE_URL}/users/{user}/lists/{list_name}/items",
            model_validator=GetItemsOnAPersonalList200ResponseInner.from_dict,
        )

    def get_collection_items(self, user: str, media_type: MediaType):
        """Get collections from Trakt with pagination support."""

        from schemas.trakt import GetCollection200ResponseInner

        return self._fetch_data(
            url=f"{self.BASE_URL}/users/{user}/collection/{media_type}",
            model_validator=GetCollection200ResponseInner.from_dict,
        )

    def get_trending_movies(self, limit: int | None = None):
        """Get trending movies from Trakt with pagination support."""

        from schemas.trakt import GetTrendingMovies200ResponseInner

        return self._fetch_data(
            url=f"{self.BASE_URL}/movies/trending",
            model_validator=GetTrendingMovies200ResponseInner.from_dict,
            limit=limit,
        )

    def get_trending_shows(self, limit: int | None = None):
        """Get trending shows from Trakt with pagination support."""

        from schemas.trakt import GetTrendingShows200ResponseInner

        return self._fetch_data(
            url=f"{self.BASE_URL}/shows/trending",
            model_validator=GetTrendingShows200ResponseInner.from_dict,
            limit=limit,
        )

    def get_popular_movies(self, limit: int | None = None):
        """Get popular movies from Trakt with pagination support."""

        from schemas.trakt import GetPopularMovies200ResponseInner

        return self._fetch_data(
            url=f"{self.BASE_URL}/movies/popular",
            model_validator=GetPopularMovies200ResponseInner.from_dict,
            limit=limit,
        )

    def get_popular_shows(self, limit: int | None = None):
        """Get popular items from Trakt with pagination support."""

        from schemas.trakt import GetPopularShows200ResponseInner

        return self._fetch_data(
            url=f"{self.BASE_URL}/shows/popular",
            model_validator=GetPopularShows200ResponseInner.from_dict,
            limit=limit,
        )

    def get_most_played_movies(self, period: str = "weekly", limit: int | None = None):
        """Get most played items from Trakt with pagination support."""

        from schemas.trakt import GetTheMostPlayedMovies200ResponseInner

        return self._fetch_data(
            url=f"{self.BASE_URL}/movies/watched/{period}",
            model_validator=GetTheMostPlayedMovies200ResponseInner.from_dict,
            limit=limit,
        )

    def get_most_played_shows(self, period: str = "weekly", limit: int | None = None):
        """Get most played items from Trakt with pagination support."""

        from schemas.trakt import GetTheMostPlayedShows200ResponseInner

        return self._fetch_data(
            url=f"{self.BASE_URL}/shows/watched/{period}",
            model_validator=GetTheMostPlayedShows200ResponseInner.from_dict,
            limit=limit,
        )

    def extract_user_list_from_url(
        self, url: str
    ) -> tuple[str, str] | tuple[None, None]:
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

    def get_aliases(self, imdb_id: str | None, item_type: str) -> dict[str, list[str]]:
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
                aliases = dict[str, list[str]]({})

                from schemas.trakt import GetAllMovieAliases200ResponseInner

                response_data = (
                    PageResponse[GetAllMovieAliases200ResponseInner]
                    .model_validate({"data": response.json()})
                    .data
                )

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
        except Exception as e:
            logger.debug(
                f"Failed to get aliases for {imdb_id} with type {item_type}: {e}"
            )

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

    def build_oauth_url(self) -> str:
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

            class OAuthTokenResponse(BaseModel):
                access_token: str
                refresh_token: str

            token_data = OAuthTokenResponse.model_validate(response.json())

            self.settings.access_token = token_data.access_token
            self.settings.refresh_token = token_data.refresh_token

            settings_manager.save()  # Save the tokens to settings

            return True
        else:
            logger.error(f"Failed to obtain OAuth token: {response.status_code}")
            return False
