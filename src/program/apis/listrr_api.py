from kink import di
from loguru import logger
from requests.exceptions import HTTPError

from program.apis.trakt_api import TraktAPI
from program.media.item import MediaItem
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    Session,
    create_service_session,
)


class ListrrAPIError(Exception):
    """Base exception for ListrrAPI related errors"""

class ListrrRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, base_url=base_url, response_type=ResponseType.SIMPLE_NAMESPACE, custom_exception=ListrrAPIError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> ResponseObject:
        return super()._request(method, endpoint, **kwargs)

class ListrrAPI:
    """Handles Listrr API communication"""

    def __init__(self, api_key: str):
        self.BASE_URL = "https://listrr.pro"
        self.api_key = api_key
        self.headers = {"X-Api-Key": self.api_key}
        session = create_service_session()
        session.headers.update(self.headers)
        self.request_handler = ListrrRequestHandler(session, base_url=self.BASE_URL)
        self.trakt_api = di[TraktAPI]

    def validate(self):
        return self.request_handler.execute(HttpMethod.GET, "")

    def get_items_from_Listrr(self, content_type, content_lists) -> list[MediaItem] | list[str]:  # noqa: C901, PLR0912
        """Fetch unique IMDb IDs from Listrr for a given type and list of content."""
        unique_ids: set[str] = set()
        if not content_lists:
            return list(unique_ids)

        for list_id in content_lists:
            if not list_id or len(list_id) != 24:
                continue

            page, total_pages = 1, 1
            while page <= total_pages:
                try:
                    url = f"api/List/{content_type}/{list_id}/ReleaseDate/Descending/{page}"
                    response = self.request_handler.execute(HttpMethod.GET, url)
                    data = response.data
                    total_pages = data.pages if hasattr(data, "pages") else 1
                    for item in data.items if hasattr(data, "items") else []:

                        try:
                            imdb_id = item.imDbId or (
                                self.trakt_api.get_imdbid_from_tmdb(item.tmDbId) 
                                if content_type == "Movies" and item.tmDbId 
                                else None
                            )

                            if not imdb_id:
                                continue
                            if imdb_id in unique_ids:
                                logger.warning(f"Skipping duplicate item {imdb_id}")
                                continue

                            unique_ids.add(imdb_id)
                        except AttributeError:
                            logger.warning(f"Skipping item {item} as it does not have an IMDb ID or TMDb ID")
                            continue
                except HTTPError as e:
                    if e.response.status_code in [400, 404, 429, 500]:
                        break
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                    break
                page += 1
        return list(unique_ids)
