"""Composite indexer that uses TMDB for movies and TVDB for TV shows"""

import time
from typing import Generator, Union

from kink import di
from loguru import logger

from program.media.item import MediaItem, Movie, Show
from program.services.indexers.base import BaseIndexer
from program.services.indexers.tmdb_indexer import TMDBIndexer
from program.services.indexers.tvdb_indexer import TVDBIndexer


class CompositeIndexer(BaseIndexer):
    """Entry point to indexing. Composite indexer that delegates to appropriate service based on media type."""
    key = "CompositeIndexer"

    def __init__(self):
        super().__init__()
        self.key = "compositeindexer"
        self.tmdb_indexer = di[TMDBIndexer]
        self.tvdb_indexer = di[TVDBIndexer]

    def run(self, in_item: MediaItem, log_msg: bool = True) -> Generator[Union[Movie, Show], None, None]:
        """Run the appropriate indexer based on item type."""
        if not in_item:
            logger.error("Item is None")
            return

        item_type = in_item.type or "mediaitem"

        if item_type == "movie" or (in_item.tmdb_id and not in_item.tvdb_id):
            yield from self.tmdb_indexer.run(in_item, log_msg)
        elif item_type in ["show", "season", "episode"] or (in_item.tvdb_id and not in_item.tmdb_id):
            yield from self.tvdb_indexer.run(in_item, log_msg)

        elif item_type == "mediaitem":
            item = None

            if not item:
                movie_result = self.tmdb_indexer.run(in_item, log_msg=False)
                item = next(movie_result, None)

            if not item:
                show_result = self.tvdb_indexer.run(in_item, log_msg=False)
                item = next(show_result, None)

            if item:
                yield item
                return

        logger.warning(f"Unknown item type, cannot index {in_item.log_string}.. skipping")
        return