"""Trakt content module"""

from datetime import datetime, timedelta

from kink import di
from loguru import logger
from requests import RequestException

from program.apis.trakt_api import TraktAPI
from program.media.item import MediaItem
from program.settings.manager import settings_manager


class TraktContent:
    """Content class for Trakt"""

    def __init__(self):
        self.key = "trakt"
        self.settings = settings_manager.settings.content.trakt
        self.api = di[TraktAPI]
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.last_update = None
        logger.success("Trakt initialized!")

    def validate(self) -> bool:
        """Validate Trakt settings."""
        try:
            if not self.settings.enabled:
                return False
            if not self.settings.api_key:
                logger.error("Trakt API key is not set.")
                return False
            response = self.api.validate()
            if not getattr(response.data, "name", None):
                logger.error("Invalid user settings received from Trakt.")
                return False
            return True
        except ConnectionError:
            logger.error("Connection error during Trakt validation.")
            return False
        except TimeoutError:
            logger.error("Timeout error during Trakt validation.")
            return False
        except RequestException as e:
            logger.error(f"Request exception during Trakt validation: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Exception during Trakt validation: {str(e)}")
            return False

    def run(self):
        """Fetch media from Trakt and yield Movie, Show, or MediaItem instances."""
        watchlist_ids = self._get_watchlist(self.settings.watchlist) if self.settings.watchlist else []
        collection_ids = self._get_collection(self.settings.collection) if self.settings.collection else []
        user_list_ids = self._get_list(self.settings.user_lists) if self.settings.user_lists else []

        # Check if it's the first run or if a day has passed since the last update
        current_time = datetime.now()
        if self.last_update is None or (current_time - self.last_update) > timedelta(days=1):
            trending_ids = self._get_trending_items() if self.settings.fetch_trending else []
            popular_ids = self._get_popular_items() if self.settings.fetch_popular else []
            most_watched_ids = self._get_most_watched_items() if self.settings.fetch_most_watched else []
            self.last_update = current_time
            logger.log("TRAKT", "Updated trending, popular, and most watched items.")
        else:
            trending_ids = []
            popular_ids = []
            most_watched_ids = []
            logger.log("TRAKT", "Skipped updating trending, popular, and most watched items (last update was less than a day ago).")

        # Combine all IMDb IDs and types into a set to avoid duplicates
        all_ids = set(watchlist_ids + collection_ids + user_list_ids + trending_ids + popular_ids + most_watched_ids)

        items_to_yield = []
        for imdb_id, _ in all_ids:
            items_to_yield.append(MediaItem({"imdb_id": imdb_id, "requested_by": self.key}))

        if not items_to_yield:
            return

        logger.info(f"Fetched {len(items_to_yield)} items from trakt")
        yield items_to_yield

    def _get_watchlist(self, watchlist_users: list) -> list:
        """Get IMDb IDs from Trakt watchlist"""
        if not watchlist_users:
            return []
        imdb_ids = []
        for user in watchlist_users:
            items = self.api.get_watchlist_items(user)
            imdb_ids.extend(self._extract_imdb_ids(items))
        return imdb_ids

    def _get_collection(self, collection_users: list) -> list:
        """Get IMDb IDs from Trakt collection"""
        if not collection_users:
            return []
        imdb_ids = []
        for user in collection_users:
            items = self.api.get_collection_items(user, "movies")
            items.extend(self.api.get_collection_items(user, "shows"))
            imdb_ids.extend(self._extract_imdb_ids(items))
        return imdb_ids


    def _get_list(self, list_items: list) -> list:
        """Get IMDb IDs from Trakt user list"""
        if not list_items or not any(list_items):
            return []
        imdb_ids = []
        for url in list_items:
            user, list_name = self.api.extract_user_list_from_url(url)
            if not user or not list_name:
                logger.error(f"Invalid list URL: {url}")
                continue

            items = self.api.get_user_list(user, list_name)
            for item in items:
                if hasattr(item, "movie"):
                    imdb_id = getattr(item.movie.ids, "imdb", None)
                    if imdb_id:
                        imdb_ids.append((imdb_id, "movie"))
                elif hasattr(item, "show"):
                    imdb_id = getattr(item.show.ids, "imdb", None)
                    if imdb_id:
                        imdb_ids.append((imdb_id, "show"))
        return imdb_ids

    def _get_trending_items(self) -> list:
        """Get IMDb IDs from Trakt trending items"""
        trending_movies = self.api.get_trending_items("movies", self.settings.trending_count)
        trending_shows = self.api.get_trending_items("shows", self.settings.trending_count)
        return self._extract_imdb_ids(trending_movies[:self.settings.trending_count] + trending_shows[:self.settings.trending_count])

    def _get_popular_items(self) -> list:
        """Get IMDb IDs from Trakt popular items"""
        popular_movies = self.api.get_popular_items("movies", self.settings.popular_count)
        popular_shows = self.api.get_popular_items( "shows", self.settings.popular_count)
        return self._extract_imdb_ids_with_none_type(popular_movies[:self.settings.popular_count] + popular_shows[:self.settings.popular_count])

    def _get_most_watched_items(self) -> list:
        """Get IMDb IDs from Trakt popular items"""
        most_watched_movies = self.api.get_most_watched_items( "movies", self.settings.most_watched_period, self.settings.most_watched_count)
        most_watched_shows = self.api.get_most_watched_items( "shows", self.settings.most_watched_period, self.settings.most_watched_count)
        return self._extract_imdb_ids(most_watched_movies[:self.settings.most_watched_count] + most_watched_shows[:self.settings.most_watched_count])

    def _extract_imdb_ids(self, items: list) -> list:
        """Extract IMDb IDs and types from a list of items"""
        imdb_ids = []
        for item in items:
            if hasattr(item, "show"):
                ids = getattr(item.show, "ids", None)
                if ids:
                    imdb_id = getattr(ids, "imdb", None)
                    if imdb_id:
                        imdb_ids.append((imdb_id, "show"))
            elif hasattr(item, "movie"):
                ids = getattr(item.movie, "ids", None)
                if ids:
                    imdb_id = getattr(ids, "imdb", None)
                    if imdb_id:
                        imdb_ids.append((imdb_id, "movie"))
        return imdb_ids

    @staticmethod
    def _extract_imdb_ids_with_none_type(items: list) -> list:
        """Extract IMDb IDs from a list of items, returning None for type"""
        imdb_ids = []
        for item in items:
            ids = getattr(item, "ids", None)
            if ids:
                imdb_id = getattr(ids, "imdb", None)
                if imdb_id:
                    imdb_ids.append((imdb_id, None))
        return imdb_ids