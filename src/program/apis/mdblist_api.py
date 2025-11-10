from program.utils.request import SmartSession


class MdblistAPIError(Exception):
    """Base exception for MdblistAPI related errors"""


class MdblistAPI:
    """Handles Mdblist API communication"""

    BASE_URL = "https://mdblist.com"

    def __init__(self, api_key: str):
        self.api_key = api_key

        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits={
                "mdblist.com": {
                    # 60 calls per minute
                    "rate": 1,
                    "capacity": 60,
                }
            },
            retries=3,
            backoff_factor=0.3,
        )

    def validate(self):
        return self.session.get(
            "api/user",
            params={
                "apikey": self.api_key,
            },
        )

    def my_limits(self):
        """Wrapper for mdblist api method 'My limits'"""

        response = self.session.get(
            "api/user",
            params={
                "apikey": self.api_key,
            },
        )

        return response.data

    def list_items_by_id(self, list_id: int):
        """Wrapper for mdblist api method 'List items'"""

        response = self.session.get(
            f"api/lists/{str(list_id)}/items",
            params={
                "apikey": self.api_key,
            },
        )

        return response.data

    def list_items_by_url(self, url: str):
        url = url if url.endswith("/") else f"{url}/"
        url = url if url.endswith("json/") else f"{url}json/"
        response = self.session.get(
            url,
            params={
                "apikey": self.api_key,
            },
        )

        return response.data
