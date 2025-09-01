"""Composite indexer that uses TMDB for movies and TVDB for TV shows"""

from typing import Generator, Union

from kink import di
from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.indexers.base import BaseIndexer
from program.services.indexers.tmdb_indexer import TMDBIndexer
from program.services.indexers.tvdb_indexer import TVDBIndexer


class CompositeIndexer(BaseIndexer):
    """Composite indexer that delegates to appropriate service based on media type"""
    key = "CompositeIndexer"

    def __init__(self):
        super().__init__()
        self.key = "compositeindexer"
        # Initialize both indexers
        self.tmdb_indexer = di[TMDBIndexer]
        self.tvdb_indexer = di[TVDBIndexer]

    def run(self, in_item: MediaItem, log_msg: bool = True) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Run the appropriate indexer based on item type."""
        if not in_item:
            logger.error("Item is None")
            return

        # Determine item type - handle the case where it might be a MediaItem with only imdb_id
        item_type = in_item.type if hasattr(in_item, "type") else "mediaitem"
        
        # PRIORITY 1: First check if we have explicit IDs - these are the most reliable indicators
        if in_item.tvdb_id and not in_item.tmdb_id:
            logger.debug(f"Using TVDB indexer based on TVDB ID: {in_item.log_string}")
            yield from self.tvdb_indexer.run(in_item, log_msg)
            return
            
        elif in_item.tmdb_id and not in_item.tvdb_id:
            logger.debug(f"Using TMDB indexer based on TMDB ID: {in_item.log_string}")
            yield from self.tmdb_indexer.run(in_item, log_msg)
            return
        
        # PRIORITY 2: Check explicit media types
        if item_type == "movie":
            logger.debug(f"Using TMDB indexer for movie type: {in_item.log_string}")
            yield from self.tmdb_indexer.run(in_item, log_msg)
            return
            
        elif item_type in ["show", "season", "episode"]:
            logger.debug(f"Using TVDB indexer for {item_type} type: {in_item.log_string}")
            yield from self.tvdb_indexer.run(in_item, log_msg)
            return
        
        # PRIORITY 3: Handle mediaitem type where we need to make a best guess
        if item_type == "mediaitem":
            # If it has seasons attribute, it's likely a show
            if hasattr(in_item, "seasons") and in_item.seasons:
                logger.debug(f"Using TVDB indexer for mediaitem with seasons: {in_item.log_string}")
                yield from self.tvdb_indexer.run(in_item, log_msg)
                return
                
            # Otherwise try TMDB first, and if that fails, try TVDB as fallback
            logger.debug(f"Type unknown for {in_item.log_string}, trying TMDB first")
            try:
                # Try TMDB first for unknown items
                movie_result = list(self.tmdb_indexer.run(in_item, log_msg=False))
                if movie_result:
                    logger.debug(f"Successfully indexed as movie: {in_item.log_string}")
                    yield from movie_result
                else:
                    # If TMDB fails, try TVDB
                    logger.debug(f"TMDB indexing failed, trying TVDB for: {in_item.log_string}")
                    yield from self.tvdb_indexer.run(in_item, log_msg)
            except Exception as e:
                logger.error(f"TMDB indexing error for {in_item.log_string}: {str(e)}")
                # Try TVDB as fallback
                yield from self.tvdb_indexer.run(in_item, log_msg)
            return

        # Fall through case - should rarely hit this
        logger.error(f"Unknown item type: {item_type} for {in_item.log_string}")
