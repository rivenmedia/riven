from program.settings.models import TraktModel
from program.utils.request import SmartSession


class TvmazeAPIError(Exception):
    """Base exception for TvmazeApi related errors"""


class TvmazeAPI:
    """Handles TVMaze API communication"""

    BASE_URL = "https://api.tvmaze.com"

    def __init__(self, settings: TraktModel):
        self.settings = settings

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits={
                # 1000 calls per 5 minutes
                "api.tvmaze.com": {
                    "rate": 1000 // 300,
                    "capacity": 100,
                }
            },
            retries=2,
            backoff_factor=0.3,
        )
        self.session.headers.update({"Content-type": "application/json"})

    def validate(self):
        return self.session.get("lists/2")
