import os
from requests import Session

from program.settings.models import TraktModel
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    create_service_session,
    get_cache_params,
    get_rate_limit_params
)


class TvmazeAPIError(Exception):
    """Base exception for TvmazeApi related errors"""

class TvmazeRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, response_type=ResponseType.SIMPLE_NAMESPACE, request_logging: bool = False):
        super().__init__(session, response_type=response_type, custom_exception=TvmazeAPIError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> ResponseObject:
        return super()._request(method, endpoint, **kwargs)


class TvmazeAPI:
    """Handles TVMaze API communication"""
    BASE_URL = "https://api.tvmaze.com"

    def __init__(self, settings: TraktModel):
        self.settings = settings
        rate_limit_params = get_rate_limit_params(max_calls=1000, period=300)
        tvmaze_cache = get_cache_params("tvmaze", 86400)
        use_cache = os.environ.get("SKIP_TVMAZE_CACHE", "false").lower() == "true"
        session = create_service_session(rate_limit_params=rate_limit_params, use_cache=use_cache, cache_params=tvmaze_cache)
        session.headers.update({"Content-type": "application/json"})
        self.request_handler = TvmazeRequestHandler(session)

    def validate(self):
        return self.request_handler.execute(HttpMethod.GET, f"{self.BASE_URL}/lists/2")

    def get_show(self, tvdb_id: str = None, imdb_id: str = None) -> dict:
        """Wrapper for tvdb.com API show method."""
        if not tvdb_id and not imdb_id:
            return {}
        
        tvmaze_id = None
        lookup_params = {"thetvdb": tvdb_id, "imdb": imdb_id}
        lookup_param = next((key for key, value in lookup_params.items() if value), None)

        if lookup_param:
            url = f"{self.BASE_URL}/lookup/shows?{lookup_param}={lookup_params[lookup_param]}"
            response = self.request_handler.execute(HttpMethod.GET, url, timeout=30)
            if response.is_ok and response.data:
                tvmaze_id = response.data[0].id

        if tvmaze_id:
            url = f"{self.BASE_URL}/shows/{tvmaze_id}/episodes"
            response = self.request_handler.execute(HttpMethod.GET, url, timeout=30)
            return response.data if response.is_ok and response.data else {}

        return {}
