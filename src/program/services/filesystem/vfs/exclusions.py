from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Show
from program.settings.manager import settings_manager


class Exclusions:
    excluded_shows: set[str]
    excluded_movies: set[str]

    def __init__(self):
        excluded_items = settings_manager.settings.filesystem.excluded_items

        self.excluded_movies = excluded_items.movies
        self.excluded_shows = excluded_items.shows

        logger.log(
            "VFS",
            f"Excluded shows: {self.excluded_shows}. "
            f"Excluded movies: {self.excluded_movies}",
        )

    def is_excluded(self, item: MediaItem) -> bool:
        if isinstance(item, Show | Episode):
            return self._is_excluded_show(item._get_top_parent())

        if isinstance(item, Movie):
            return self._is_excluded_movie(item)

        return False

    def _is_excluded_show(self, item: Show) -> bool:
        if item.tvdb_id is None:
            return False

        return item.tvdb_id in self.excluded_shows

    def _is_excluded_movie(self, item: Movie) -> bool:
        if item.tmdb_id is None and item.imdb_id is None:
            return False

        return (
            item.tmdb_id in self.excluded_movies or item.imdb_id in self.excluded_movies
        )
