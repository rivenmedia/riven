"""Listrr API"""

from typing import Literal
from httpx_limiter.rate import Rate
from httpx_retries import Retry

from clients.listrr.listrr_pro_v1_client.client import AuthenticatedClient
from clients.listrr.listrr_pro_v1_client.models import (
    ListrrContractsEnumControllersListControllerShowListSortEnum,
    ListrrContractsEnumSortByDirectionEnum,
    ListrrContractsModelsAPIMovieDto,
    ListrrContractsModelsAPIShowDto,
)
from clients.listrr.listrr_pro_v1_client.types import Unset
from program.utils.rate_limited_async_client import RateLimitedAsyncClient


class ListrrAPIError(Exception):
    """Base exception for ListrrAPI related errors"""


class ListrrAPI:
    """Handles Listrr API communication"""

    def __init__(self, api_key: str):
        self.client = AuthenticatedClient(
            base_url="https://listrr.pro/api",
            token=api_key,
            auth_header_name="X-Api-Key",
        )

        self.client.set_async_httpx_client(
            RateLimitedAsyncClient(
                rate_limit=Rate.create(magnitude=50, duration=10),
                retry=Retry(total=3, backoff_factor=0.3),
            )
        )

    def validate(self):
        from clients.listrr.listrr_pro_v1_client.api.list_.get_api_list_my_page import (
            sync_detailed as get_my_lists_sync,
        )

        return get_my_lists_sync(client=self.client)

    def get_items_from_Listrr(
        self,
        content_type: Literal["Movies", "Shows"],
        content_lists: list[str],
    ) -> list[tuple[str | Unset | None, int | Unset]]:  # noqa: C901, PLR0912
        """Fetch unique IMDb IDs from Listrr for a given type and list of content."""
        unique_ids: set[tuple[str | Unset | None, int | Unset]] = set()

        if not content_lists:
            return list()

        if content_type == "Movies":
            from clients.listrr.listrr_pro_v1_client.api.list_.get_api_list_movies_id_sort_by_sort_by_direction_page import (
                sync as get_page,
            )
        elif content_type == "Shows":
            from clients.listrr.listrr_pro_v1_client.api.list_.get_api_list_shows_id_sort_by_sort_by_direction_page import (
                sync as get_page,
            )

        for list_id in content_lists:
            if not list_id or len(list_id) != 24:
                continue

            page, total_pages = 1, 1

            while page <= total_pages:
                response = get_page(
                    list_id,
                    sort_by=ListrrContractsEnumControllersListControllerShowListSortEnum.RELEASEDATE,
                    sort_by_direction=ListrrContractsEnumSortByDirectionEnum.DESCENDING,
                    page=page,
                    client=self.client,
                )

                if not response:
                    break

                if response.items:
                    for item in response.items:
                        if isinstance(item, ListrrContractsModelsAPIMovieDto):
                            unique_ids.add((item.im_db_id, item.tm_db_id))
                        elif isinstance(item, ListrrContractsModelsAPIShowDto):
                            unique_ids.add((item.im_db_id, item.tv_db_id))

                    page += 1

                total_pages = response.pages or 0

        return list(unique_ids)
