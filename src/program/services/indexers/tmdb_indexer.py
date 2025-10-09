"""TMDB indexer module"""

from datetime import datetime
from typing import Generator, Optional

from kink import di
from loguru import logger

from program.apis.tmdb_api import TMDBApi
from program.media.item import MediaItem, Movie
from program.services.indexers.base import BaseIndexer


class TMDBIndexer(BaseIndexer):
    """TMDB indexer class for movies"""
    key = "TMDBIndexer"

    def __init__(self):
        super().__init__()
        self.key = "tmdbindexer"
        self.api = di[TMDBApi]

    def run(self, in_item: MediaItem, log_msg: bool = True) -> Generator[Movie, None, None]:
        """Run the TMDB indexer for the given item."""
        if not in_item:
            logger.error("Item is None")
            return

        if not (in_item.imdb_id or in_item.tmdb_id):
            logger.error(f"Item {in_item.log_string} does not have an imdb_id or tmdb_id, cannot index it")
            return

        if in_item.type not in ["movie", "mediaitem"]:
            logger.debug(f"TMDB indexer skipping incorrect item type: {in_item.log_string}")
            return

        if (item := self._create_movie_from_id(in_item.imdb_id, in_item.tmdb_id)):
            item = self.copy_items(in_item, item)
            item.indexed_at = datetime.now()
            if log_msg:
                logger.log("NEW", f"Indexed Movie {item.log_string} (IMDB: {item.imdb_id}, TMDB: {item.tmdb_id})")
            yield item

        logger.error(f"Failed to index movie with ids: imdb={in_item.imdb_id}, tmdb={in_item.tmdb_id}")
        return

    def _create_movie_from_id(self, imdb_id: Optional[str] = None, tmdb_id: Optional[str] = None) -> Optional[Movie]:
        """Create a movie item from TMDB using available IDs."""
        if not imdb_id and not tmdb_id:
            logger.error("No IMDB ID or TMDB ID provided")
            return None

        movie_details = None

        try:
            # Direct lookup by TMDB ID
            if tmdb_id:
                result = self.api.get_movie_details(tmdb_id, "append_to_response=external_ids,release_dates")
                movie_details = result.data if result and result.data else None

            # Lookup via IMDB ID
            elif imdb_id:
                results = self.api.get_from_external_id("imdb_id", imdb_id)
                if (results and results.data) and not getattr(results.data, "movie_results", []):
                    logger.debug(f"IMDB ID {imdb_id} is not a movie, skipping")
                    return None

                movie_results = results.data.movie_results
                if movie_results:
                    tmdb_id = str(movie_results[0].id)
                    result = self.api.get_movie_details(tmdb_id, "append_to_response=external_ids,release_dates")
                    movie_details = result.data if result and result.data else None

        except Exception as e:
            logger.error(f"Error fetching movie details: {e}")

        if not movie_details:
            if tmdb_id:
                logger.error(f"Failed to get movie details for TMDB ID: {tmdb_id}")
            elif imdb_id:
                logger.error(f"Failed to get movie details for IMDB ID: {imdb_id}")
            else:
                logger.error("Failed to get movie details for unknown ID")
            return None

        try:
            release_date = (
                datetime.strptime(movie_details.release_date, "%Y-%m-%d")
                if getattr(movie_details, "release_date", None)
                else None
            )

            genres = [
                genre.name.lower()
                for genre in getattr(movie_details, "genres", []) or []
            ]

            country = None
            if getattr(movie_details, "production_countries", None):
                country = movie_details.production_countries[0].iso_3166_1

            # Extract rating (vote_average from TMDB, 0-10 scale)
            rating = None
            if hasattr(movie_details, "vote_average") and movie_details.vote_average:
                rating = float(movie_details.vote_average)

            # Extract US content rating (certification)
            content_rating = None
            if hasattr(movie_details, "release_dates") and movie_details.release_dates:
                # Look for US release dates
                for release_country in movie_details.release_dates.results:
                    if release_country.iso_3166_1 == "US":
                        # Get the first certification available
                        for release in release_country.release_dates:
                            if hasattr(release, "certification") and release.certification:
                                content_rating = release.certification
                                break
                        break

            movie_item = {
                "title": getattr(movie_details, "title", None),
                "year": (
                    int(movie_details.release_date[:4])
                    if getattr(movie_details, "release_date", None)
                    else None
                ),
                "tvdb_id": None,
                "tmdb_id": str(movie_details.id),
                "imdb_id": getattr(movie_details, "imdb_id", None),
                "aired_at": release_date,
                "genres": genres,
                "type": "movie",
                "requested_at": datetime.now(),
                "overview": getattr(movie_details, "overview", None),
                "country": country,
                "language": getattr(movie_details, "original_language", None),
                "is_anime": (
                    any(g in ["animation", "anime"] for g in genres)
                    and getattr(movie_details, "original_language", None) != "en"
                ),
                "aliases": {},
                "rating": rating,
                "content_rating": content_rating,
            }

            return Movie(movie_item)

        except Exception as e:
            logger.error(f"Error mapping TMDB movie data: {e}")

        return None
