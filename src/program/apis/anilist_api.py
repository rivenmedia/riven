import requests
from kink import di
from loguru import logger

from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    Session,
    create_service_session,
)

class AnilistAPIError(Exception):
    """Base exception for AnilistAPI related errors"""

class AnilistRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, base_url=base_url, response_type=ResponseType.SIMPLE_NAMESPACE, custom_exception=AnilistAPIError, request_logging=request_logging)

    def execute(self, query: str, variables: dict = None) -> ResponseObject:
        return super()._request(HttpMethod.POST, "", json={"query": query, "variables": variables or {}})

class AnilistAPI:
    """Handles AniList API communication"""

    BASE_URL = "https://graphql.anilist.co"

    def __init__(self):
        session = create_service_session()
        self.request_handler = AnilistRequestHandler(session, base_url=self.BASE_URL)

    def validate(self):
        query = """
        query {
            Media(id: 1) {
                id
                title {
                    romaji
                }
            }
        }
        """
        return self.request_handler.execute(query)

    def get_media_by_id(self, anilist_id: int):
        query = """
        query ($id: Int) {
            Media(id: $id) {
                id
                title {
                    romaji
                    english
                }
            }
        }
        """
        variables = {"id": anilist_id}
        response = self.request_handler.execute(query, variables)
        if response.is_ok:
            return response.data
        else:
            logger.error(f"Failed to fetch media with ID {anilist_id}: {response.data}")
            return None
