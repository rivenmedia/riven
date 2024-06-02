"""Trakt content module"""
import time
from types import SimpleNamespace

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get, post


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
        """Fetch media from Trakt and yield MediaItem instances."""
        current_time = time.time()
        if current_time < self.next_run_time:
            return
        
        self.next_run_time = current_time + self.settings.update_interval
        # watchlist_items = self._get_trakt_watchlist(self.settings.watchlist if self.settings.watchlist else [])
        collection_items = self._get_trakt_collections(self.settings.collections if self.settings.collections else [])
        user_list_items = self._get_trakt_list(self.settings.user_lists if self.settings.user_lists else [])
        trending_items = self._get_trending_items() if self.settings.fetch_trending else []
        popular_items = self._get_popular_items() if self.settings.fetch_popular else []
        items = list(set(collection_items + user_list_items + trending_items + popular_items))
        
        for item in items:
            imdb_id = item.get("imdb_id")
            if imdb_id in self.items_already_seen:
                continue
            self.items_already_seen.add(imdb_id)
            media_item = MediaItem({
                "imdb_id": imdb_id,
                "requested_by": self.key
            })
            yield media_item

    def _get_trakt_watchlist(self, watchlist_items: list) -> list:
        """Get items from Trakt watchlist"""
        items = []
        for url in watchlist_items:
            items.extend(get_watchlist_items(self.api_url, self.headers, url))
        return items

    def _get_trakt_collections(self, collection_items: list) -> list:
        """Get items from Trakt collections"""
        items = []
        for url in collection_items:
            items.extend(get_user_list(self.api_url, self.headers, url, "collection"))
        return items

    def _get_trakt_list(self, list_items: list) -> list:
        """Get items from Trakt user list"""
        items = []
        for url in list_items:
            items.extend(get_user_list(self.api_url, self.headers, url, "list"))
        return items

    def _get_trending_items(self) -> list:
        """Get trending items from Trakt"""
        trending_movies = get_trending_items(self.api_url, self.headers, "movies", self.settings.trending_count)
        trending_shows = get_trending_items(self.api_url, self.headers, "shows", self.settings.trending_count)
        return trending_movies + trending_shows

    def _get_popular_items(self) -> list:
        """Get popular items from Trakt"""
        popular_movies = get_popular_items(self.api_url, self.headers, "movies", self.settings.popular_count)
        popular_shows = get_popular_items(self.api_url, self.headers, "shows", self.settings.popular_count)
        return popular_movies + popular_shows


## API functions for Trakt

def fetch_paginated_data(url, headers, params):
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
                if len(data) < params["limit"]:
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
    return fetch_paginated_data(url, headers, {"limit": limit})

def get_user_list(api_url, headers, user, list_name, limit=10):
    """Get user list items from Trakt with pagination support."""
    url = f"{api_url}/users/{user}/lists/{list_name}/items"
    return fetch_paginated_data(url, headers, {"limit": limit})

def get_liked_lists(api_url, headers, limit=10):
    """Get liked lists from Trakt with pagination support."""
    url = f"{api_url}/users/likes/lists"
    return fetch_paginated_data(url, headers, {"limit": limit})

def get_recommendations(api_url, headers, media_type, limit=10):
    """Get recommendations from Trakt with pagination support."""
    url = f"{api_url}/recommendations/{media_type}"
    return fetch_paginated_data(url, headers, {"limit": limit})

def get_trending_items(api_url, headers, media_type, limit=10):
    """Get trending items from Trakt with pagination support."""
    url = f"{api_url}/trending/{media_type}"
    return fetch_paginated_data(url, headers, {"limit": limit})

def get_popular_items(api_url, headers, media_type, limit=10):
    """Get popular items from Trakt with pagination support."""
    url = f"{api_url}/popular/{media_type}"
    return fetch_paginated_data(url, headers, {"limit": limit})

def get_favorited_items(api_url, headers, user, limit=10):
    """Get favorited items from Trakt with pagination support."""
    url = f"{api_url}/users/{user}/favorites"
    return fetch_paginated_data(url, headers, {"limit": limit})