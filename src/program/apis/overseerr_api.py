"""Overseerr API client"""

from loguru import logger
from requests.exceptions import ConnectionError, RetryError
from urllib3.exceptions import MaxRetryError

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    Session,
    create_service_session,
    get_rate_limit_params,
)


class OverseerrAPIError(Exception):
    """Base exception for OverseerrAPI related errors"""

class OverseerrRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, base_url: str, request_logging: bool = False):
        super().__init__(session, base_url=base_url, response_type=ResponseType.SIMPLE_NAMESPACE, custom_exception=OverseerrAPIError, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> ResponseObject:
        return super()._request(method, endpoint, **kwargs)


class OverseerrAPI:
    """Handles Overseerr API communication"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        rate_limit_params = get_rate_limit_params(max_calls=1000, period=300)
        session = create_service_session(rate_limit_params=rate_limit_params)
        self.headers = {"X-Api-Key": self.api_key}
        session.headers.update(self.headers)
        self.request_handler = OverseerrRequestHandler(session, base_url=base_url)

    def validate(self):
        return self.request_handler.execute(HttpMethod.GET, "api/v1/auth/me", timeout=30)

    def get_media_requests(self, service_key: str) -> list[MediaItem]:
        """Get media requests from `Overseerr`"""
        try:
            response = self.request_handler.execute(HttpMethod.GET, f"api/v1/request?take={10000}&filter=approved&sort=added")
            if not response.is_ok:
                logger.error(f"Failed to fetch requests from overseerr: {response.data}")
                return []
        except (ConnectionError, RetryError, MaxRetryError) as e:
            logger.error(f"Failed to fetch requests from overseerr: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during fetching requests: {str(e)}")
            return []

        if not hasattr(response.data, "pageInfo") or getattr(response.data.pageInfo, "results", 0) == 0:
            return []

        # Lets look at approved items only that are only in the pending state
        pending_items = [
            item for item in response.data.results
            if item.status == 2 and item.media.status == 3
        ]

        media_items = []
        for item in pending_items:
            media_type = item.type
            imdb_id = item.media.imdbId
            tmdb_id = item.media.tmdbId
            tvdb_id = item.media.tvdbId

            if media_type == "tv":
                media_type = "show"

            if media_type == "movie":
                media_items.append(
                    MediaItem({
                        "imdb_id": imdb_id,
                        "tmdb_id": tmdb_id,
                        "type": media_type,
                        "requested_by": service_key,
                    })
                )
            elif media_type == "show":
                media_items.append(
                    MediaItem({
                        "imdb_id": imdb_id,
                        "tvdb_id": tvdb_id,
                        "type": media_type,
                        "requested_by": service_key,
                    })
                )

            else:
                logger.error(f"Unknown media type: {media_type}")

        return media_items

    def delete_request(self, mediaId: int) -> bool:
        """Delete request from `Overseerr`"""
        settings = settings_manager.settings.content.overseerr
        headers = {"X-Api-Key": settings.api_key}
        try:
            response = self.request_handler.execute(HttpMethod.DELETE, f"api/v1/request/{mediaId}", headers=headers)
            logger.debug(f"Deleted request {mediaId} from overseerr")
            return response.is_ok
        except Exception as e:
            logger.error(f"Failed to delete request from overseerr: {str(e)}")
            return False

    def mark_processing(self, mediaId: int) -> bool:
        """Mark item as processing in overseerr"""
        try:
            response = self.request_handler.execute(HttpMethod.POST, f"api/v1/media/{mediaId}/pending", data={"is4k": False})
            logger.info(f"Marked media {mediaId} as processing in overseerr")
            return response.is_ok
        except Exception as e:
            logger.error(f"Failed to mark media as processing in overseerr with id {mediaId}: {str(e)}")
            return False

    def mark_partially_available(self, mediaId: int) -> bool:
        """Mark item as partially available in overseerr"""
        try:
            response = self.request_handler.execute(HttpMethod.POST, f"api/v1/media/{mediaId}/partial", data={"is4k": False})
            logger.info(f"Marked media {mediaId} as partially available in overseerr")
            return response.is_ok
        except Exception as e:
            logger.error(f"Failed to mark media as partially available in overseerr with id {mediaId}: {str(e)}")
            return False

    def mark_completed(self, mediaId: int) -> bool:
        """Mark item as completed in overseerr"""
        try:
            response = self.request_handler.execute(HttpMethod.POST, f"api/v1/media/{mediaId}/available", data={"is4k": False})
            logger.info(f"Marked media {mediaId} as completed in overseerr")
            return response.is_ok
        except Exception as e:
            logger.error(f"Failed to mark media as completed in overseerr with id {mediaId}: {str(e)}")
            return False

# Statuses for Media Requests endpoint /api/v1/request:
# item.status:
# 1 = PENDING APPROVAL,
# 2 = APPROVED,
# 3 = DECLINED

# Statuses for Media Info endpoint /api/v1/media:
# item.media.status:
# 1 = UNKNOWN,
# 2 = PENDING,
# 3 = PROCESSING,
# 4 = PARTIALLY_AVAILABLE,
# 5 = AVAILABLE