from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING
from loguru import logger

from program.media.item import Episode, Movie, Show
from program.settings.manager import settings_manager

if TYPE_CHECKING:
    from program.media.item import MediaItem


class Exclusions:
    excluded_shows: set[str]
    excluded_movies: set[str]

    def __init__(self):
        excluded_items = settings_manager.settings.filesystem.excluded_items

        self.excluded_movies = excluded_items.movies
        self.excluded_shows = excluded_items.shows

    def is_excluded(self, item: "MediaItem") -> bool:
        is_excluded_movie = self._is_excluded_movie(item)
        is_excluded_show = self._is_excluded_show(item._get_top_parent())

        return is_excluded_movie or is_excluded_show

    def _is_excluded_show(self, item: Show) -> bool:
        if item.tvdb_id is None:
            return False

        return str(item.tvdb_id) in self.excluded_shows

    def _is_excluded_movie(self, item: Movie) -> bool:
        if item.tmdb_id is None and item.imdb_id is None:
            return False

        return (
            str(item.tmdb_id) in self.excluded_movies
            or str(item.imdb_id) in self.excluded_movies
        )

    @contextmanager
    def exclusion_check(
        self,
        item: "MediaItem",
        type: str,
    ) -> Generator["MediaItem | None"]:
        try:
            if self.is_excluded(item):
                logger.trace(f"Item {item.log_string} is excluded from {type}.")

                yield None
            else:
                yield item
        except Exception as e:
            logger.error(
                f"Error during exclusion check for item {item.log_string}: {e}"
            )

            yield None


exclusions = Exclusions()
