from typing import Union

from kink import di
from loguru import logger
from requests.exceptions import ConnectionError, RetryError
from urllib3.exceptions import MaxRetryError

from program.apis.trakt_api import TraktAPI
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
        self.trakt_api = di[TraktAPI]
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
            imdb_id = self.get_imdb_id(item.media)
            if imdb_id:
                media_items.append(
                    MediaItem({
                        "imdb_id": imdb_id,
                        "requested_by": service_key,
                        "overseerr_id": item.media.id
                    })
                )
            elif item.media.tmdbId:
                logger.debug(f"Skipping {item.type} with TMDb ID {item.media.tmdbId} due to missing IMDb ID")
            elif item.media.tvdbId:
                logger.debug(f"Skipping {item.type} with TVDb ID {item.media.tvdbId} due to missing IMDb ID")
            else:
                logger.debug(f"Skipping {item.type} with Overseerr ID {item.media.id} due to missing IMDb ID")
        return media_items


    def get_imdb_id(self, data) -> str | None:
        """Get imdbId for item from overseerr"""
        if data.mediaType == "show":
            external_id = data.tvdbId
            data.mediaType = "tv"
        else:
            external_id = data.tmdbId

        try:
            response = self.request_handler.execute(HttpMethod.GET, f"api/v1/{data.mediaType}/{external_id}?language=en")
        except (ConnectionError, RetryError, MaxRetryError) as e:
            logger.error(f"Failed to fetch media details from overseerr: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during fetching media details: {str(e)}")
            return None

        if not response.is_ok or not hasattr(response.data, "externalIds"):
            return None

        imdb_id = getattr(response.data.externalIds, "imdbId", None)
        if imdb_id:
            return imdb_id

        # Try alternate IDs if IMDb ID is not available
        alternate_ids = [("tmdbId", self.trakt_api.get_imdbid_from_tmdb)]
        for id_attr, fetcher in alternate_ids:
            external_id_value = getattr(response.data.externalIds, id_attr, None)
            if external_id_value:
                _type = data.media_type
                if _type == "tv":
                    _type = "show"
                try:
                    new_imdb_id: Union[str, None] = fetcher(external_id_value, type=_type)
                    if not new_imdb_id:
                        continue
                    return new_imdb_id
                except Exception as e:
                    logger.error(f"Error fetching alternate ID: {str(e)}")
                    continue

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