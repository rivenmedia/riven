"""Trakt content module"""
import time
from types import SimpleNamespace
from urllib.parse import urlparse

import regex

from program.media.item import MediaItem, Movie, Show
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get


class TraktContent:
    """Content class for Trakt"""

    def __init__(self):
        self.key = "trakt"
        self.api_url = "https://api.trakt.tv"
        self.settings = settings_manager.settings.content.trakt
        self.headers = {
            "Content-type": "application/json",
            "trakt-api-key": self.settings.api_key,
            "trakt-api-version": "2"
        }
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.next_run_time = 0
        self.items_already_seen = set()  # Use a set for faster lookups
        self.items_to_yield = {}
        logger.success("Trakt initialized!")

    def validate(self) -> bool:
        """Validate Trakt settings."""
        if not self.settings.enabled:
            logger.warning("Trakt is set to disabled.")
            return False
        if not self.settings.api_key:
            logger.error("Trakt API key is not set.")
            return False

        # Simple GET request to test Trakt API key
        response = get(f"{self.api_url}/lists/2", additional_headers=self.headers)
        if not response.is_ok:
            logger.error(f"Error connecting to Trakt: {response.status_code}")
            return False

        if not getattr(response.data, 'name', None):
            logger.error("Invalid user settings received from Trakt.")
            return False
        return True

    def run(self):
        """Fetch media from Trakt and yield Movie or Show instances."""
        current_time = time.time()
        if current_time < self.next_run_time:
            return

        self.next_run_time = current_time + self.settings.update_interval
        watchlist_ids = self._get_watchlist(self.settings.watchlist)
        collection_ids = self._get_collections(self.settings.collections)
        user_list_ids = self._get_list(self.settings.user_lists)
        trending_ids = self._get_trending_items() if self.settings.fetch_trending else []
        popular_ids = self._get_popular_items() if self.settings.fetch_popular else []

        # Combine all IMDb IDs and types
        all_items = watchlist_ids + collection_ids + user_list_ids + trending_ids + popular_ids
        all_ids = set(all_items)
        logger.log("TRAKT", f"Fetched {len(all_ids)} unique IMDb IDs from Trakt.")

        for imdb_id, item_type in all_ids:
            if imdb_id in self.items_already_seen or not imdb_id:
                continue
            self.items_already_seen.add(imdb_id)
            
            if item_type == "movie":
                media_item = Movie({
                    "imdb_id": imdb_id,
                    "requested_by": self.key
                })
            else:
                media_item = Show({
                    "imdb_id": imdb_id,
                    "requested_by": self.key
                })
            
            yield media_item
        self.items_to_yield.clear()

    def _get_watchlist(self, watchlist_items: list) -> list:
        """Get IMDb IDs from Trakt watchlist"""
        if not watchlist_items:
            logger.warning("No watchlist items configured.")
            return []
        imdb_ids = []
        for url in watchlist_items:
            match = regex.match(r'https://trakt.tv/users/([^/]+)/watchlist', url)
            if not match:
                logger.error(f"Invalid watchlist URL: {url}")
                continue
            user = match.group(1)
            items = get_watchlist_items(self.api_url, self.headers, user)
            imdb_ids.extend(self._extract_imdb_ids(items))
        return imdb_ids

    def _get_collections(self, collection_items: list) -> list:
        """Get IMDb IDs from Trakt collections"""
        if not collection_items:
            logger.warning("No collection items configured.")
            return []
        imdb_ids = []
        for url in collection_items:
            match = regex.match(r'https://trakt.tv/users/([^/]+)/collection', url)
            if not match:
                logger.error(f"Invalid collection URL: {url}")
                continue
            user = match.group(1)
            items = get_user_list(self.api_url, self.headers, user, "collection")
            imdb_ids.extend(self._extract_imdb_ids(items))
        return imdb_ids

    def _get_list(self, list_items: list) -> list:
        """Get IMDb IDs from Trakt user list"""
        if not list_items:
            logger.warning("No user list items configured.")
            return []
        imdb_ids = []
        for url in list_items:
            match = regex.match(r'https://trakt.tv/users/([^/]+)/lists/([^/]+)', url)
            if not match:
                logger.error(f"Invalid list URL: {url}")
                continue
            user, list_name = match.groups()
            list_name = urlparse(url).path.split('/')[-1]
            items = get_user_list(self.api_url, self.headers, user, list_name)
            imdb_ids.extend(self._extract_imdb_ids(items))
        return imdb_ids

    def _get_trending_items(self) -> list:
        """Get IMDb IDs from Trakt trending items"""
        trending_movies = get_trending_items(self.api_url, self.headers, "movies", self.settings.trending_count)
        trending_shows = get_trending_items(self.api_url, self.headers, "shows", self.settings.trending_count)
        return self._extract_imdb_ids(trending_movies + trending_shows)

    def _get_popular_items(self) -> list:
        """Get IMDb IDs from Trakt popular items"""
        popular_movies = get_popular_items(self.api_url, self.headers, "movies", self.settings.popular_count)
        popular_shows = get_popular_items(self.api_url, self.headers, "shows", self.settings.popular_count)
        return self._extract_imdb_ids(popular_movies + popular_shows)

    def _extract_imdb_ids(self, items: list) -> list:
        """Extract IMDb IDs and types from a list of items"""
        imdb_ids = []
        for item in items:
            show = getattr(item, "show", None)
            if show:
                ids = getattr(show, "ids", None)
                if ids:
                    imdb_id = getattr(ids, "imdb", None)
                    if imdb_id:
                        imdb_ids.append((imdb_id, "show"))
            else:
                ids = getattr(item, "ids", None)
                if ids:
                    imdb_id = getattr(ids, "imdb", None)
                    if imdb_id:
                        imdb_ids.append((imdb_id, "movie"))
        return imdb_ids


## API functions for Trakt

def _fetch_data(url, headers, params):
    """Fetch paginated data from Trakt API."""
    all_data = []
    page = 1
    while True:
        try:
            response = get(url, params={**params, "page": page}, additional_headers=headers)
            if response.is_ok:
                data = response.data
                if not data:
                    break
                all_data.extend(data)
                if len(data) <= params["limit"]:
                    break
                page += 1
            else:
                logger.error(f"Failed to fetch data: {response.status_code}")
                break
        except Exception as e:
            logger.error(f"Error fetching data: {str(e)}")
            break
    return all_data

def get_watchlist_items(api_url, headers, user, limit=10):
    """Get watchlist items from Trakt with pagination support."""
    url = f"{api_url}/users/{user}/watchlist"
    return _fetch_data(url, headers, {"limit": limit})

def get_user_list(api_url, headers, user, list_name, limit=10):
    """Get user list items from Trakt with pagination support."""
    url = f"{api_url}/users/{user}/lists/{list_name}/items"
    return _fetch_data(url, headers, {"limit": limit})

def get_liked_lists(api_url, headers, limit=10):
    """Get liked lists from Trakt with pagination support."""
    url = f"{api_url}/users/likes/lists"
    return _fetch_data(url, headers, {"limit": limit})

def get_recommendations(api_url, headers, media_type, limit=10):
    """Get recommendations from Trakt with pagination support."""
    url = f"{api_url}/recommendations/{media_type}"
    return _fetch_data(url, headers, {"limit": limit})

def get_trending_items(api_url, headers, media_type, limit=10):
    """Get trending items from Trakt with pagination support."""
    url = f"{api_url}/{media_type}/trending"
    return _fetch_data(url, headers, {"limit": limit})

def get_popular_items(api_url, headers, media_type, limit=10):
    """Get popular items from Trakt with pagination support."""
    url = f"{api_url}/{media_type}/popular"
    return _fetch_data(url, headers, {"limit": limit})

def get_favorited_items(api_url, headers, user, limit=10):
    """Get favorited items from Trakt with pagination support."""
    url = f"{api_url}/users/{user}/favorites"
    return _fetch_data(url, headers, {"limit": limit})