"""Overseerr API client"""

from loguru import logger

from program.media.item import MediaItem
from program.utils.request import SmartSession, get_hostname_from_url


class OverseerrAPIError(Exception):
    """Base exception for OverseerrAPI related errors"""


class OverseerrAPI:
    """Handles Overseerr API communication"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

        rate_limits = {
            get_hostname_from_url(self.base_url): {"rate": 1000/300, "capacity": 1000}  # 1000 calls per 5 minutes
        }
        
        self.session = SmartSession(
            base_url=base_url,
            rate_limits=rate_limits,
            retries=3,
            backoff_factor=0.3
        )
        self.session.headers.update({"X-Api-Key": self.api_key})

    def validate(self):
        """Validate API connection"""
        try:
            return self.session.get("api/v1/auth/me", timeout=15)
        except Exception as e:
            logger.error(f"Overseerr validation failed: {e}")
            return None

    def get_media_requests(self, service_key: str) -> list[MediaItem]:
        """Get media requests from `Overseerr`"""
        try:
            response = self.session.get(f"api/v1/request?take={10000}&filter=approved&sort=added")
            if not response.ok or not hasattr(response.data, "pageInfo") or getattr(response.data.pageInfo, "results", 0) == 0:
                if not response.ok:
                    logger.error(f"Failed to get response from overseerr: {response.data}")
                elif not hasattr(response.data, "pageInfo") or getattr(response.data.pageInfo, "results", 0) == 0:
                    logger.debug("No user approved requests found from overseerr")
                return []
        except Exception as e:
            logger.error(f"Failed to get response from overseerr: {str(e)}")
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
                new_item = MediaItem({"imdb_id": imdb_id, "tmdb_id": tmdb_id, "requested_by": service_key})
                media_items.append(new_item)
            elif media_type == "show":
                new_item = MediaItem({"imdb_id": imdb_id, "tvdb_id": tvdb_id, "requested_by": service_key})
                media_items.append(new_item)
            else:
                logger.error(f"Unknown media type: {media_type}")

        return media_items

    def delete_request(self, mediaId: int) -> bool:
        """Delete request from `Overseerr`"""
        try:
            response = self.session.delete(f"api/v1/request/{mediaId}")
            logger.debug(f"Deleted request {mediaId} from overseerr")
            return response.ok
        except Exception as e:
            logger.error(f"Failed to delete request from overseerr: {str(e)}")
            return False

    def mark_processing(self, mediaId: int) -> bool:
        """Mark item as processing in overseerr"""
        try:
            response = self.session.put(f"api/v1/request/{mediaId}", json={"status": 3})
            logger.debug(f"Marked request {mediaId} as processing in overseerr")
            return response.ok
        except Exception as e:
            logger.error(f"Failed to mark request as processing in overseerr: {str(e)}")
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