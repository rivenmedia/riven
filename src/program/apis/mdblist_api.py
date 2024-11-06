from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    Session,
    create_service_session,
    get_rate_limit_params,
)


class MdblistAPIError(Exception):
    """Base exception for MdblistAPI related errors"""

class MdblistRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, api_key: str, request_logging: bool = False):
        self.api_key = api_key
        super().__init__(session, base_url=base_url, response_type=ResponseType.SIMPLE_NAMESPACE, custom_exception=MdblistAPIError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, ignore_base_url: bool = False, **kwargs) -> ResponseObject:
        return super()._request(method, endpoint, ignore_base_url=ignore_base_url, params={"apikey": self.api_key}, **kwargs)


class MdblistAPI:
    """Handles Mdblist API communication"""
    BASE_URL = "https://mdblist.com"

    def __init__(self, api_key: str):
        rate_limit_params = get_rate_limit_params(per_minute=60)
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.request_handler = MdblistRequestHandler(session, base_url=self.BASE_URL, api_key=api_key)

    def validate(self):
        return self.request_handler.execute(HttpMethod.GET, f"api/user")

    def my_limits(self):
        """Wrapper for mdblist api method 'My limits'"""
        response = self.request_handler.execute(HttpMethod.GET,f"api/user")
        return response.data

    def list_items_by_id(self, list_id: int):
        """Wrapper for mdblist api method 'List items'"""
        response = self.request_handler.execute(HttpMethod.GET,f"api/lists/{str(list_id)}/items")
        return response.data

    def list_items_by_url(self, url: str):
        url = url if url.endswith("/") else f"{url}/"
        url = url if url.endswith("json/") else f"{url}json/"
        response = self.request_handler.execute(HttpMethod.GET, url, ignore_base_url=True)
        return response.data