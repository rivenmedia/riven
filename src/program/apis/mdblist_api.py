from program.utils.request import get_rate_limit_params, create_service_session, get, ping


class MdblistAPI:
    """Handles Mdblist API communication"""
    BASE_URL = "https://mdblist.com"

    def __init__(self, api_key: str):
        self.api_key = api_key

        rate_limit_params = get_rate_limit_params(per_minute=60)

        self.session = create_service_session(
            rate_limit_params=rate_limit_params,
            use_cache=False
        )

    def validate(self):
        return ping(session=self.session, url=f"{self.BASE_URL}/api/user?apikey={self.api_key}")

    def my_limits(self):
        """Wrapper for mdblist api method 'My limits'"""
        response = get(session=self.session, url=f"{self.BASE_URL}/api/user?apikey={self.api_key}")
        return response.data

    def list_items_by_id(self, list_id: int):
        """Wrapper for mdblist api method 'List items'"""
        response = get(session=self.session,
                       url=f"{self.BASE_URL}/api/lists/{str(list_id)}/items?apikey={self.api_key}"
                       )
        return response.data

    def list_items_by_url(self, url: str):
        url = url if url.endswith("/") else f"{url}/"
        url = url if url.endswith("json/") else f"{url}json/"
        response = get(session=self.session, url=url, params={"apikey": self.api_key})
        return response.data