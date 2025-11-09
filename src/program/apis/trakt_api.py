import os
import re
from datetime import datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, List, Optional, Union
from urllib.parse import urlencode

from loguru import logger
from requests import RequestException

from program.settings.manager import settings_manager
from program.settings.models import TraktModel
from program.utils.request import SmartSession

if TYPE_CHECKING:
    from program.media.item import Episode, MediaItem, Movie, Season, Show


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

        rate_limits = {
            "api.trakt.tv": {
                "rate": 1000 / 300,
                "capacity": 1000,
            }  # 1000 calls per 5 minutes
        }

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
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

    def get_liked_lists(self):
        """Get liked lists from Trakt with pagination support."""
        url = f"{self.BASE_URL}/users/likes/lists"
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

    def get_favorited_items(self, user, limit=10):
        """Get favorited items from Trakt with pagination support."""
        url = f"{self.BASE_URL}/users/{user}/favorites"
        return self._fetch_data(url, {"limit": limit})

    def get_movie_release_dates(self, imdb_id: str):  # takes 2-char country code
        """Get release dates for a movie from Trakt"""
        url = f"{self.BASE_URL}/movies/{imdb_id}/releases"
        return self._fetch_data(url, {})

    def extract_user_list_from_url(self, url) -> tuple:
        """Extract user and list name from Trakt URL"""

        def match_full_url(url: str) -> tuple:
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

    def get_show(self, imdb_id: str) -> dict:
        """Wrapper for trakt.tv API show method."""
        if not imdb_id:
            return {}
        url = f"{self.BASE_URL}/shows/{imdb_id}/seasons?extended=episodes,full"
        response = self.session.get(url, timeout=30)
        return response.data if response.ok and response.data else {}

    def get_aliases(self, imdb_id: str, item_type: str) -> dict[str, list[str]]:
        """
        Wrapper for trakt.tv API show method.

        Returns:
            Dict[str, list[str]]: A dictionary where keys are country codes and values are lists of alias names.

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
                for ns in response.data:
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

    def create_item_from_imdb_id(
        self, imdb_id: str, type: str = None
    ) -> Optional["MediaItem"]:
        """Wrapper for trakt.tv API search method."""
        url = f"{self.BASE_URL}/search/imdb/{imdb_id}?extended=full"
        if type:
            url += f"&type={type}"

        try:
            response = self.session.get(url, timeout=30)
        except TraktAPIError as e:
            logger.error(f"Failed to create item using imdb id: {imdb_id} - {str(e)}")
            return None
        if not response.ok or not response.data:
            logger.error(
                f"Failed to create item using imdb id: {imdb_id}"
            )  # This returns an empty list for response.data
            return None

        data = next((d for d in response.data if d.type == type), None)
        if not data:
            clause = lambda x: (
                x.type == type if type else x in ["show", "movie", "season", "episode"]
            )
            data = next((d for d in response.data if clause), None)

        return (
            self.map_item_from_data(getattr(data, data.type), data.type)
            if data
            else None
        )

    def get_imdbid_from_tmdb(self, tmdb_id: str, type: str = "movie") -> Optional[str]:
        """Wrapper for trakt.tv API search method."""
        url = f"{self.BASE_URL}/search/tmdb/{tmdb_id}"  # ?extended=full
        response = self.session.get(url, timeout=30)
        if not response.ok or not response.data:
            return None
        imdb_id = self._get_imdb_id_from_list(
            response.data, id_type="tmdb", _id=tmdb_id, type=type
        )
        if imdb_id and imdb_id.startswith("tt"):
            return imdb_id
        logger.error(f"Failed to fetch imdb_id for tmdb_id: {tmdb_id}")
        return None

    def get_imdbid_from_tvdb(self, tvdb_id: str, type: str = "show") -> Optional[str]:
        """Wrapper for trakt.tv API search method."""
        url = f"{self.BASE_URL}/search/tvdb/{tvdb_id}"
        response = self.session.get(url, timeout=30)
        if not response.ok or not response.data:
            return None
        imdb_id = self._get_imdb_id_from_list(
            response.data, id_type="tvdb", _id=tvdb_id, type=type
        )
        if imdb_id and imdb_id.startswith("tt"):
            return imdb_id
        logger.error(f"Failed to fetch imdb_id for tvdb_id: {tvdb_id}")
        return None

    def resolve_short_url(self, short_url) -> Union[str, None]:
        """Resolve short URL to full URL"""
        try:
            response = self.session.get(
                endpoint=short_url,
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

    def map_item_from_data(
        self, data, item_type: str, show_genres: List[str] = None
    ) -> Optional["MediaItem"]:
        """Map trakt.tv API data to MediaItemContainer."""
        if item_type not in ["movie", "show", "season", "episode"]:
            logger.debug(
                f"Unknown item type {item_type} for {data.title} not found in list of acceptable items"
            )
            return None

        formatted_aired_at = self._get_formatted_date(data, item_type)
        genres = getattr(data, "genres", None) or show_genres

        item = {
            "title": getattr(data, "title", None),
            "year": getattr(data, "year", None),
            "status": getattr(data, "status", None),
            "aired_at": formatted_aired_at,
            "trakt_id": getattr(data.ids, "trakt", None),
            "imdb_id": getattr(data.ids, "imdb", None),
            "tvdb_id": getattr(data.ids, "tvdb", None),
            "tmdb_id": getattr(data.ids, "tmdb", None),
            "genres": genres,
            "network": getattr(data, "network", None),
            "country": getattr(data, "country", None),
            "language": getattr(data, "language", None),
            "requested_at": datetime.now(),
            "type": item_type,
        }

        item["is_anime"] = self._is_anime(item)

        match item_type:
            case "movie":
                item["aliases"] = self.get_aliases(item["imdb_id"], "movies")
                return Movie(item)
            case "show":
                item["aliases"] = self.get_aliases(item["imdb_id"], "shows")
                return Show(item)
            case "season":
                item["number"] = data.number
                return Season(item)
            case "episode":
                item["number"] = data.number
                return Episode(item)
            case _:
                logger.error(
                    f"Unknown item type {item_type} for {data.title} not found in list of acceptable items"
                )
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

    def _get_imdb_id_from_list(
        self,
        namespaces: List[SimpleNamespace],
        id_type: str = None,
        _id: str = None,
        type: str = None,
    ) -> Optional[str]:
        """Get the imdb_id from the list of namespaces."""
        if not any([id_type, _id, type]):
            return None

        for ns in namespaces:
            if (
                type == "movie"
                and hasattr(ns, "movie")
                and hasattr(ns.movie, "ids")
                and hasattr(ns.movie.ids, "imdb")
            ):
                if str(getattr(ns.movie.ids, id_type)) == str(_id):
                    return ns.movie.ids.imdb
            elif (
                type == "show"
                and hasattr(ns, "show")
                and hasattr(ns.show, "ids")
                and hasattr(ns.show.ids, "imdb")
            ):
                if str(getattr(ns.show.ids, id_type)) == str(_id):
                    return ns.show.ids.imdb
            elif (
                type == "season"
                and hasattr(ns, "season")
                and hasattr(ns.season, "ids")
                and hasattr(ns.season.ids, "imdb")
            ):
                if str(getattr(ns.season.ids, id_type)) == str(_id):
                    return ns.season.ids.imdb
            elif (
                type == "episode"
                and hasattr(ns, "episode")
                and hasattr(ns.episode, "ids")
                and hasattr(ns.episode.ids, "imdb")
            ):
                if str(getattr(ns.episode.ids, id_type)) == str(_id):
                    return ns.episode.ids.imdb
        return None

    def _get_formatted_date(self, data, item_type: str) -> Optional[datetime]:
        """Get the formatted aired date from the data."""
        if item_type in ["show", "season", "episode"] and (
            first_aired := getattr(data, "first_aired", None)
        ):
            return datetime.strptime(first_aired, "%Y-%m-%dT%H:%M:%S.%fZ")
        if item_type == "movie" and (released := getattr(data, "released", None)):
            return datetime.strptime(released, "%Y-%m-%d")
        return None

    def _is_anime(self, item: dict) -> bool:
        """Check if the item is an anime."""
        if item.get("type") in ("season", "episode"):
            # We get this from show item and copy it down to season and episode. No need to check again.
            return False

        if not item.get("genres") or item.get("country") == "us":
            return False

        if not any(
            genre in item.get("genres", [])
            for genre in ["animation", "donghua", "anime"]
        ):
            return False

        if item.get("country", "") not in ["jp", "kr", "cn", "hk"]:
            return False

        return True
