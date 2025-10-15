from program.settings.models import TraktModel
from program.utils.request import SmartSession


class TvmazeAPIError(Exception):
    """Base exception for TvmazeApi related errors"""


class TvmazeAPI:
    """Handles TVMaze API communication"""

    BASE_URL = "https://api.tvmaze.com"

    def __init__(self, settings: TraktModel):
        self.settings = settings

        rate_limits = {
            "api.tvmaze.com": {
                "rate": 1000 / 300,
                "capacity": 100,
            }  # 1000 calls per 5 minutes
        }

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits=rate_limits,
            retries=2,
            backoff_factor=0.3,
        )
        self.session.headers.update({"Content-type": "application/json"})

    def validate(self):
        return self.session.get("lists/2")

    def get_show(self, tvdb_id: str = None, imdb_id: str = None) -> dict:
        """Wrapper for tvdb.com API show method."""
        if not tvdb_id and not imdb_id:
            return {}

        tvmaze_id = None
        lookup_params = {"thetvdb": tvdb_id, "imdb": imdb_id}
        lookup_param = next(
            (key for key, value in lookup_params.items() if value), None
        )

        if lookup_param:
            url = f"lookup/shows?{lookup_param}={lookup_params[lookup_param]}"
            response = self.session.get(url, timeout=30)
            if response.ok and response.data:
                tvmaze_id = response.data[0].id

        if tvmaze_id:
            url = f"shows/{tvmaze_id}/episodes"
            response = self.session.get(url, timeout=30)
            return response.data if response.ok and response.data else {}

        return {}
