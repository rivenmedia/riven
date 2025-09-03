"""Composite indexer that uses TMDB for movies and TVDB for TV shows"""

from typing import Generator, Union

from kink import di
from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
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
            logger.debug(f"Using TMDB indexer for movie type: {in_item.log_string}")
            yield from self.tmdb_indexer.run(in_item, log_msg)
        elif item_type in ["show", "season", "episode"] or (in_item.tvdb_id and not in_item.tmdb_id):
            logger.debug(f"Using TVDB indexer for {item_type} type: {in_item.log_string}")
            yield from self.tvdb_indexer.run(in_item, log_msg)

        elif item_type == "mediaitem":
            if tvdb_result := self.tvdb_indexer.run(in_item, log_msg=False):
                logger.debug(f"Successfully indexed as show: {in_item.log_string}")
                yield from tvdb_result
            elif movie_result := self.tmdb_indexer.run(in_item, log_msg=False):
                logger.debug(f"Successfully indexed as movie: {in_item.log_string}")
                yield from movie_result

        logger.warning(f"Unknown item type, cannot index {in_item.log_string}.. tossing it")
        return