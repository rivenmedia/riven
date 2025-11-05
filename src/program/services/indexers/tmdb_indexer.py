"""TMDB indexer module"""

from datetime import datetime
from typing import Generator, Optional

from kink import di
from loguru import logger

from program.apis.tmdb_api import TMDBApi
from program.apis.trakt_api import TraktAPI
from program.media.item import MediaItem, Movie
from program.services.indexers.base import BaseIndexer


class TMDBIndexer(BaseIndexer):
    """TMDB indexer class for movies"""

    key = "TMDBIndexer"

    def __init__(self):
        super().__init__()
        self.key = "tmdbindexer"
        self.api = di[TMDBApi]
        self.trakt_api = di[TraktAPI]

    def run(
        self, in_item: MediaItem, log_msg: bool = True
    ) -> Generator[Movie, None, None]:
        """Run the TMDB indexer for the given item."""
        if not in_item:
            logger.error("Item is None")
            return

        if not (in_item.imdb_id or in_item.tmdb_id):
            logger.error(
                f"Item {in_item.log_string} does not have an imdb_id or tmdb_id, cannot index it"
            )
            return

        if in_item.type not in ["movie", "mediaitem"]:
            logger.debug(
                f"TMDB indexer skipping incorrect item type: {in_item.log_string}"
            )
            return

        # Scenario 1: Fresh indexing - create new Movie from API data
        if in_item.type == "mediaitem":
            if item := self._create_movie_from_id(in_item.imdb_id, in_item.tmdb_id):
                item = self.copy_items(in_item, item)
                item.indexed_at = datetime.now()
                if log_msg:
                    logger.debug(
                        f"Indexed Movie {item.log_string} (IMDB: {item.imdb_id}, TMDB: {item.tmdb_id})"
                    )
                yield item
                return

        # Scenario 2: Reindexing existing Movie - update in-place
        elif in_item.type == "movie":
            if self._update_movie_metadata(in_item):
                in_item.indexed_at = datetime.now()
                if log_msg:
                    logger.debug(
                        f"Reindexed Movie {in_item.log_string} (IMDB: {in_item.imdb_id}, TMDB: {in_item.tmdb_id})"
                    )
                yield in_item
                return

        logger.error(
            f"Failed to index movie with ids: imdb={in_item.imdb_id}, tmdb={in_item.tmdb_id}"
        )
        return

    def _update_movie_metadata(self, movie: Movie) -> bool:
        """Update an existing Movie object with fresh TMDB metadata.

        Returns True if successful, False otherwise.
        """
        try:
            # Fetch fresh data from TMDB API
            tmdb_id = movie.tmdb_id
            imdb_id = movie.imdb_id

            if not tmdb_id and not imdb_id:
                logger.error(f"Movie {movie.log_string} has no TMDB or IMDB ID")
                return False

            # Get movie details from API
            movie_details = None
            if tmdb_id:
                result = self.api.get_movie_details(
                    tmdb_id, "append_to_response=external_ids,release_dates"
                )
                movie_details = result.data if result and result.data else None
            elif imdb_id:
                results = self.api.get_from_external_id("imdb_id", imdb_id)
                if results and results.data:
                    movie_results = results.data.movie_results
                    if movie_results:
                        tmdb_id = str(movie_results[0].id)
                        result = self.api.get_movie_details(
                            tmdb_id, "append_to_response=external_ids,release_dates"
                        )
                        movie_details = result.data if result and result.data else None

            if not movie_details:
                logger.error(f"Could not fetch TMDB data for {movie.log_string}")
                return False

            # Parse release date
            release_date = None
            if getattr(movie_details, "release_date", None):
                try:
                    release_date = datetime.strptime(
                        movie_details.release_date, "%Y-%m-%d"
                    )
                except (ValueError, TypeError):
                    pass

            # Extract genres
            genres = [
                genre.name.lower()
                for genre in getattr(movie_details, "genres", []) or []
            ]

            # Extract country
            country = None
            if getattr(movie_details, "production_countries", None):
                country = movie_details.production_countries[0].iso_3166_1

            # Extract rating
            rating = None
            if hasattr(movie_details, "vote_average") and movie_details.vote_average:
                rating = float(movie_details.vote_average)

            # Extract US content rating
            content_rating = None
            if hasattr(movie_details, "release_dates") and movie_details.release_dates:
                for release_country in movie_details.release_dates.results:
                    if release_country.iso_3166_1 == "US":
                        for release in release_country.release_dates:
                            if (
                                hasattr(release, "certification")
                                and release.certification
                            ):
                                content_rating = release.certification
                                break
                        break

            # Aliases
            aliases = self.trakt_api.get_aliases(imdb_id, "movies") or {}

            poster_path = getattr(movie_details, "poster_path", None)
            full_poster_url = None
            if poster_path:
                full_poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"

            # Update the Movie object's attributes
            movie.title = getattr(movie_details, "title", None)
            movie.poster_path = full_poster_url
            movie.year = (
                int(movie_details.release_date[:4])
                if getattr(movie_details, "release_date", None)
                else None
            )
            movie.tmdb_id = str(movie_details.id)
            movie.imdb_id = getattr(movie_details, "imdb_id", None)
            movie.aired_at = release_date
            movie.genres = genres
            movie.country = country
            movie.language = getattr(movie_details, "original_language", None)
            movie.is_anime = (
                any(g in ["animation", "anime"] for g in genres)
                and getattr(movie_details, "original_language", None) != "en"
            )
            movie.aliases = aliases
            movie.rating = rating
            movie.content_rating = content_rating

            return True

        except Exception as e:
            logger.error(f"Error updating movie metadata: {str(e)}")
            return False

    def _create_movie_from_id(
        self, imdb_id: Optional[str] = None, tmdb_id: Optional[str] = None
    ) -> Optional[Movie]:
        """Create a movie item from TMDB using available IDs."""
        if not imdb_id and not tmdb_id:
            logger.error("No IMDB ID or TMDB ID provided")
            return None

        movie_details = None

        try:
            # Direct lookup by TMDB ID
            if tmdb_id:
                result = self.api.get_movie_details(
                    tmdb_id, "append_to_response=external_ids,release_dates"
                )
                movie_details = result.data if result and result.data else None

            # Lookup via IMDB ID
            elif imdb_id:
                results = self.api.get_from_external_id("imdb_id", imdb_id)
                if (results and results.data) and not getattr(
                    results.data, "movie_results", []
                ):
                    logger.debug(f"IMDB ID {imdb_id} is not a movie, skipping")
                    return None

                movie_results = results.data.movie_results
                if movie_results:
                    tmdb_id = str(movie_results[0].id)
                    result = self.api.get_movie_details(
                        tmdb_id, "append_to_response=external_ids,release_dates"
                    )
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
                            if (
                                hasattr(release, "certification")
                                and release.certification
                            ):
                                content_rating = release.certification
                                break
                        break

            # Aliases
            _imdb_id = getattr(movie_details, "imdb_id", None)
            aliases = self.trakt_api.get_aliases(_imdb_id, "movies") or {}

            poster_path = getattr(movie_details, "poster_path", None)
            full_poster_url = None
            if poster_path:
                full_poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"

            movie_item = {
                "title": getattr(movie_details, "title", None),
                "poster_path": full_poster_url,
                "year": (
                    int(movie_details.release_date[:4])
                    if getattr(movie_details, "release_date", None)
                    else None
                ),
                "tvdb_id": None,
                "tmdb_id": str(movie_details.id),
                "imdb_id": _imdb_id,
                "aired_at": release_date,
                "genres": genres,
                "type": "movie",
                "requested_at": datetime.now(),
                "country": country,
                "language": getattr(movie_details, "original_language", None),
                "is_anime": (
                    any(g in ["animation", "anime"] for g in genres)
                    and getattr(movie_details, "original_language", None) != "en"
                ),
                "aliases": aliases,
                "rating": rating,
                "content_rating": content_rating,
            }

            return Movie(movie_item)

        except Exception as e:
            logger.error(f"Error mapping TMDB movie data: {e}")

        return None
