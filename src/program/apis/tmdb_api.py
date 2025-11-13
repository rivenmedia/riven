"""TMDB API client"""

from program.utils.request import SmartSession

TMDB_READ_ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiJlNTkxMmVmOWFhM2IxNzg2Zjk3ZTE1NWY1YmQ3ZjY1MSIsInN1YiI6IjY1M2NjNWUyZTg5NGE2MDBmZjE2N2FmYyIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.xrIXsMFJpI1o1j5g2QpQcFP1X3AfRjFA5FlBFO5Naw8"  # noqa: S105


class TMDBApiError(Exception):
    """Base exception for TMDB API related errors"""


class TMDBApi:
    """Handles TMDB API communication"""

    def __init__(self):
        self.BASE_URL = "https://api.themoviedb.org/3"

        rate_limits = {
            # 50 requests per second
            "api.themoviedb.org": {
                "rate": 50,
                "capacity": 1000,
            }
        }

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
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

    def get_movie_details(self, movie_id: str, params: str = ""):
        """Get movie details"""

        return self.session.get(f"movie/{movie_id}?{params}")
