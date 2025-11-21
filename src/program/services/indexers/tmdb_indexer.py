"""TMDB indexer module"""

from datetime import datetime

from kink import di
from loguru import logger

from program.apis.tmdb_api import TMDBApi
from program.apis.trakt_api import TraktAPI
from program.media.item import MediaItem, Movie
from program.services.indexers.base import BaseIndexer
from program.core.runner import MediaItemGenerator, RunnerResult


class TMDBIndexer(BaseIndexer):
    """TMDB indexer class for movies"""

    def __init__(self):
        super().__init__()

        self.api = di[TMDBApi]
        self.trakt_api = di[TraktAPI]

    def run(
        self,
        in_item: MediaItem,
        log_msg: bool = True,
    ) -> MediaItemGenerator[Movie]:
        """Run the TMDB indexer for the given item."""

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

                yield RunnerResult(media_items=[item])
                return

        # Scenario 2: Re-indexing existing Movie - update in-place
        elif isinstance(in_item, Movie):
            if self._update_movie_metadata(in_item):
                in_item.indexed_at = datetime.now()
                if log_msg:
                    logger.debug(
                        f"Re-indexed Movie {in_item.log_string} (IMDB: {in_item.imdb_id}, TMDB: {in_item.tmdb_id})"
                    )

                yield RunnerResult(media_items=[in_item])
                return

        logger.error(
            f"Failed to index movie with ids: imdb={in_item.imdb_id}, tmdb={in_item.tmdb_id}"
        )
        return

    def _update_movie_metadata(self, movie: Movie) -> bool:
        """
        Update an existing Movie object with fresh TMDB metadata.

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
            if imdb_id and not tmdb_id:
                results = self.api.get_from_external_id(
                    external_source="imdb_id",
                    external_id=str(imdb_id),
                )

                if results:
                    movie_results = results.movie_results

                    if movie_results:
                        tmdb_id = str(movie_results[0].id)

            if not tmdb_id:
                logger.error(f"Movie {movie.log_string} has no TMDB ID resolved")
                return False

            movie_details = (
                self.api.get_movie_details_with_external_ids_and_release_dates(
                    movie_id=str(tmdb_id),
                )
            )

            # Parse release date
            release_date = None

            if movie_details.release_date:
                try:
                    release_date = datetime.strptime(
                        movie_details.release_date,
                        "%Y-%m-%d",
                    )
                except (ValueError, TypeError):
                    pass

            # Extract genres
            genres = [
                genre.name.lower() for genre in movie_details.genres or [] if genre.name
            ]

            # Extract country
            country = (
                movie_details.production_countries[0].iso_3166_1
                if movie_details.production_countries
                else None
            )

            # Extract rating
            rating = (
                float(movie_details.vote_average)
                if movie_details.vote_average
                else None
            )

            # Extract US content rating
            content_rating = None

            if movie_details.release_dates.results:
                for release_country in movie_details.release_dates.results:
                    if (
                        release_country.iso_3166_1 == "US"
                        and release_country.release_dates
                    ):
                        for release in release_country.release_dates:
                            if release.certification:
                                content_rating = release.certification
                                break

                        break

            # Aliases
            aliases = self.trakt_api.get_aliases(movie_details.imdb_id, "movies") or {}

            full_poster_url = (
                f"https://image.tmdb.org/t/p/w500{movie_details.poster_path}"
                if movie_details.poster_path
                else None
            )

            assert movie_details.title

            # Update the Movie object's attributes
            movie.title = movie_details.title
            movie.poster_path = full_poster_url
            movie.year = (
                int(movie_details.release_date[:4])
                if movie_details.release_date
                else None
            )
            movie.tmdb_id = str(movie_details.id)
            movie.imdb_id = movie_details.imdb_id
            movie.aired_at = release_date
            movie.genres = genres
            movie.country = country
            movie.language = movie_details.original_language
            movie.is_anime = (
                any(g in ["animation", "anime"] for g in genres)
                and movie_details.original_language != "en"
            )
            movie.aliases = aliases
            movie.rating = rating
            movie.content_rating = content_rating

            return True

        except Exception as e:
            logger.error(f"Error updating movie metadata: {str(e)}")
            return False

    def _create_movie_from_id(
        self,
        imdb_id: str | None = None,
        tmdb_id: str | None = None,
    ) -> Movie | None:
        """Create a movie item from TMDB using available IDs."""

        if not imdb_id and not tmdb_id:
            logger.error("No IMDB ID or TMDB ID provided")
            return None

        movie_details = None

        try:
            # Lookup via IMDB ID
            if imdb_id and not tmdb_id:
                results = self.api.get_from_external_id("imdb_id", imdb_id)

                assert results

                movie_results = results.movie_results

                if not movie_results:
                    logger.debug(f"IMDB ID {imdb_id} is not a movie, skipping")
                    return None

                tmdb_id = str(movie_results[0].id)

            if not tmdb_id:
                logger.error("No TMDB ID resolved for movie")
                return None

            movie_details = (
                self.api.get_movie_details_with_external_ids_and_release_dates(tmdb_id)
            )
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
                if movie_details.release_date
                else None
            )

            genres = [
                genre.name.lower() for genre in movie_details.genres or [] if genre.name
            ]

            country = (
                movie_details.production_countries[0].iso_3166_1
                if movie_details.production_countries
                else None
            )

            # Extract rating (vote_average from TMDB, 0-10 scale)
            rating = (
                float(movie_details.vote_average)
                if movie_details.vote_average
                else None
            )

            # Extract US content rating (certification)
            content_rating = None

            if movie_details.release_dates.results:
                # Look for US release dates
                for release_country in movie_details.release_dates.results:
                    if (
                        release_country.iso_3166_1 == "US"
                        and release_country.release_dates
                    ):
                        # Get the first certification available
                        for release in release_country.release_dates:
                            if release.certification:
                                content_rating = release.certification
                                break

                        break

            # Aliases
            aliases = self.trakt_api.get_aliases(movie_details.imdb_id, "movies") or {}

            full_poster_url = (
                f"https://image.tmdb.org/t/p/w500{movie_details.poster_path}"
                if movie_details.poster_path
                else None
            )

            movie_item = {
                "title": movie_details.title,
                "poster_path": full_poster_url,
                "year": (
                    int(movie_details.release_date[:4])
                    if movie_details.release_date
                    else None
                ),
                "tvdb_id": None,
                "tmdb_id": str(object=movie_details.id),
                "imdb_id": movie_details.imdb_id,
                "aired_at": release_date,
                "genres": genres,
                "type": "movie",
                "requested_at": datetime.now(),
                "country": country,
                "language": movie_details.original_language,
                "is_anime": (
                    any(g in ["animation", "anime"] for g in genres)
                    and movie_details.original_language != "en"
                ),
                "aliases": aliases,
                "rating": rating,
                "content_rating": content_rating,
            }

            return Movie(movie_item)
        except Exception as e:
            logger.error(f"Error mapping TMDB movie data: {e}")

        return None
