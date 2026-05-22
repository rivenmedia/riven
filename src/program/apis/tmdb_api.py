"""TMDB API client"""

from schemas.tmdb.models.find_by_id200_response import FindById200Response
from schemas.tmdb.models.movie_details200_response import MovieDetails200Response
from schemas.tmdb.models.movie_external_ids200_response import (
    MovieExternalIds200Response,
)
from schemas.tmdb.models.movie_release_dates200_response import (
    MovieReleaseDates200Response,
)

from program.services.rate_limit import http_rate_limit_map, register_http_limit
from program.utils.request import SmartSession


class MovieDetailsWithExtras(MovieDetails200Response):
    external_ids: MovieExternalIds200Response
    release_dates: MovieReleaseDates200Response

TMDB_READ_ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJlNTkxMmVmOWFhM2IxNzg2Zjk3ZTE1NWY1YmQ3ZjY1MSIsInN1YiI6IjY1M2NjNWUyZTg5NGE2MDBmZjE2N2FmYyIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.xrIXsMFJpI1o1j5g2QpQcFP1X3AfRjFA5FlBFO5Naw8"  # noqa: S105


class TMDBApiError(Exception):
    """Base exception for TMDB API related errors"""


class TMDBApi:
    """Handles TMDB API communication"""

    def __init__(self):
        self.BASE_URL = "https://api.themoviedb.org/3"

        register_http_limit(
            "tmdb",
            "api.themoviedb.org",
            rate=40,
            capacity=1000,
            label="API (40/s)",
        )
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limit_map=http_rate_limit_map("tmdb", "api.themoviedb.org"),
            retries=2,
            backoff_factor=0.3,
        )

        self.session.headers.update(
            {
                "Authorization": f"Bearer {TMDB_READ_ACCESS_TOKEN}",
            }
        )

    def get_from_external_id(self, external_source: str, external_id: str):
        """Get TMDB item from external ID"""

        response = self.session.get(
            f"find/{external_id}?external_source={external_source}"
        )

        return FindById200Response.from_dict(response.json())

    def get_movie_details_with_external_ids_and_release_dates(self, movie_id: str):
        """Get movie details with external IDs and release dates appended"""

        response = self.session.get(
            f"movie/{movie_id}?append_to_response=external_ids,release_dates"
        )

        data = response.json()

        movie_details = MovieDetails200Response.from_dict(data)
        external_ids = MovieExternalIds200Response.from_dict(data.get("external_ids"))
        release_dates = MovieReleaseDates200Response.from_dict(
            data.get("release_dates")
        )

        assert movie_details
        assert external_ids
        assert release_dates

        return MovieDetailsWithExtras.model_validate(
            {
                **movie_details.model_dump(),
                "external_ids": external_ids,
                "release_dates": release_dates,
            }
        )
