"""Overseerr API client"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from loguru import logger

from program.utils.request import SmartSession, get_hostname_from_url

if TYPE_CHECKING:
    from program.media.item import MediaItem

type ItemType = Literal["tv", "movie"]


class OverseerrAPIError(Exception):
    """Base exception for OverseerrAPI related errors"""


class OverseerrAPI:
    """Handles Overseerr API communication"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

        self.session = SmartSession(
            base_url=base_url,
            rate_limits={
                # 1000 calls per 5 minutes, retries=3, backoff_factor=0.3
                get_hostname_from_url(self.base_url): {
                    "rate": 1000 // 300,
                    "capacity": 1000,
                }
            },
        )

        self.session.headers.update({"X-Api-Key": self.api_key})

    def validate(self):
        """Validate API connection"""

        try:
            response = self.session.get("api/v1/auth/me", timeout=15)

            return response
        except Exception as e:
            logger.error(f"Overseerr validation failed: {e}")

            return None

    def get_media_requests(
        self, service_key: str, filter: str = "approved", take: int = 10000
    ) -> list["MediaItem"]:
        """Get media requests from `Overseerr`"""

        from program.media.item import MediaItem

        url = f"api/v1/request?take={take}&sort=added"

        if filter:
            url += f"&filter={filter}"

        try:
            response = self.session.get(url)

            @dataclass
            class ResponseData:
                """Response data structure from Overseerr API"""

                @dataclass
                class Item:
                    """Item structure from Overseerr API"""

                    @dataclass
                    class Media:
                        """Media structure from Overseerr API"""

                        tmdbId: int
                        tvdbId: int
                        status: int

                    type: ItemType
                    media: Media
                    status: int

                @dataclass
                class PageInfo:
                    """PageInfo structure from Overseerr API"""

                    totalResults: int
                    results: int
                    page: int
                    totalPages: int

                pageInfo: PageInfo
                results: list[Item]

            if not response.ok:
                logger.error(f"Failed to get response from overseerr: {response.data}")

                return []

            response_data = ResponseData(**response.json())

            if response_data.pageInfo.results == 0:
                logger.debug("No user approved requests found from overseerr")

                return []

        except Exception as e:
            logger.error(f"Failed to get response from overseerr: {str(e)}")

            return []

        # Lets look at approved items only that are only in the pending state
        pending_items = response_data.results

        if filter == "approved":
            pending_items = [
                item
                for item in response_data.results
                if item.status == 2 and item.media.status == 3
            ]

        media_items: list[MediaItem] = []

        for item in pending_items:
            media_type = item.type
            tmdb_id = item.media.tmdbId
            tvdb_id = item.media.tvdbId

            if media_type == "tv":
                media_type = "show"

            if media_type == "movie":
                new_item = MediaItem({"tmdb_id": tmdb_id, "requested_by": service_key})
                media_items.append(new_item)
            elif media_type == "show":
                new_item = MediaItem({"tvdb_id": tvdb_id, "requested_by": service_key})
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
