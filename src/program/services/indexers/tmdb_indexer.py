"""TMDB indexer module"""

from datetime import datetime
from typing import Generator, Optional, Union

from kink import di
from loguru import logger

from program.apis.tmdb_api import TMDBApi
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.indexers.base import BaseIndexer


class TMDBIndexer(BaseIndexer):
    """TMDB indexer class for movies"""
    key = "TMDBIndexer"

    def __init__(self):
        super().__init__()
        self.key = "tmdbindexer"
        self.ids = []
        self.api = di[TMDBApi]

    def run(self, in_item: MediaItem, log_msg: bool = True) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Run the TMDB indexer for the given item."""
        if not in_item:
            logger.error("Item is None")
            return
            
        # For TMDB, we'll use different ID strategies depending on what we have
        imdb_id = in_item.imdb_id
        tmdb_id = in_item.tmdb_id
        
        if not (imdb_id or tmdb_id):
            logger.error(f"Item {in_item.log_string} does not have an imdb_id or tmdb_id, cannot index it")
            return

        # TMDB indexer will primarily handle movies
        if in_item.type not in ["movie", "mediaitem"]:
            logger.debug(f"TMDB indexer skipping non-movie item: {in_item.log_string}")
            return
            
        # Get movie details from TMDB
        item = self._create_movie_from_ids(imdb_id, tmdb_id)
        
        if not item:
            logger.error(f"Failed to index movie with ids: imdb={imdb_id}, tmdb={tmdb_id}")
            return

        item = self.copy_items(in_item, item)
        item.indexed_at = datetime.now()

        if log_msg:
            logger.info(f"Indexed movie {item.log_string} (IMDB: {item.imdb_id}, TMDB: {item.tmdb_id})")

        yield item
        
    def _create_movie_from_ids(self, imdb_id: Optional[str] = None, tmdb_id: Optional[str] = None) -> Optional[Movie]:
        """Create a movie item from TMDB using available IDs."""
        if not imdb_id and not tmdb_id:
            logger.error("No IMDB ID or TMDB ID provided")
            return None

        movie_details = None
        
        # First try TMDB ID if available
        if tmdb_id:
            movie_details = self.api.get_movie_details(tmdb_id, "append_to_response=external_ids")
            
        # If that fails or no TMDB ID, try IMDB ID
        if not movie_details and imdb_id:
            # Use the find endpoint to get TMDB data from IMDB ID
            results = self.api.get_from_external_id("imdb_id", imdb_id)
            if results and hasattr(results, 'movie_results') and results.movie_results:
                # Get the first movie result and fetch full details
                tmdb_id = results.movie_results[0].id
                movie_details = self.api.get_movie_details(str(tmdb_id), "append_to_response=external_ids")
        
        if not movie_details:
            return None
            
        # Map TMDB movie details to our Movie object
        try:
            # Convert release date to datetime
            release_date = None
            if hasattr(movie_details, 'release_date') and movie_details.release_date:
                release_date = datetime.strptime(movie_details.release_date, "%Y-%m-%d")
                
            # Extract genres
            genres = []
            if hasattr(movie_details, 'genres') and movie_details.genres:
                genres = [genre.name.lower() for genre in movie_details.genres]
            
            # Get country
            country = None
            if hasattr(movie_details, 'production_countries') and movie_details.production_countries:
                country = movie_details.production_countries[0].iso_3166_1
            
            # Create movie item
            movie_item = {
                "title": movie_details.title,
                "year": int(movie_details.release_date[:4]) if hasattr(movie_details, 'release_date') and movie_details.release_date else None,
                "tmdb_id": str(movie_details.id),
                "imdb_id": movie_details.imdb_id if hasattr(movie_details, 'imdb_id') else None,
                "aired_at": release_date,
                "genres": genres,
                "type": "movie",
                "requested_at": datetime.now(),
                "overview": movie_details.overview if hasattr(movie_details, 'overview') else None,
                "country": country,
                "language": movie_details.original_language if hasattr(movie_details, 'original_language') else None,
                "is_anime": any(g in ["animation", "anime"] for g in genres) and 
                           (not hasattr(movie_details, 'original_language') or 
                            movie_details.original_language != "en")
            }
            
            return Movie(movie_item)
        except Exception as e:
            logger.error(f"Error creating movie from TMDB data: {str(e)}")
            return None
