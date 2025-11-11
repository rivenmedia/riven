from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager


class Exclusions:
    excluded_shows: list[str]
    excluded_movies: list[str]

    def __init__(self):
        excluded_items = settings_manager.settings.filesystem.excluded_items

        self.excluded_movies = excluded_items.movies
        self.excluded_shows = excluded_items.shows

        logger.debug(
            f"excluded shows: {self.excluded_shows}, excluded movies: {self.excluded_movies}"
        )

    def is_excluded(self, item: MediaItem) -> bool:
        if item.type == "show":
            return self._is_excluded_show(item.tvdb_id)
        elif item.type == "movie":
            return self._is_excluded_movie(item.tmdb_id)

        return False

    def _is_excluded_show(self, show_id: str | None) -> bool:
        if show_id is None:
            return False

        return show_id in self.excluded_shows

    def _is_excluded_movie(self, movie_id: str | None) -> bool:
        if movie_id is None:
            return False

        return movie_id in self.excluded_movies
