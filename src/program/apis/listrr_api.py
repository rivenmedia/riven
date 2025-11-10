"""Listrr API"""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Literal
from program.utils.request import SmartSession


class ListrrAPIError(Exception):
    """Base exception for ListrrAPI related errors"""


class ListrrAPI:
    """Handles Listrr API communication"""

    def __init__(self, api_key: str):
        self.BASE_URL = "https://listrr.pro/api"
        self.api_key = api_key
        self.headers = {"X-Api-Key": self.api_key}
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits={
                "listrr.pro": {
                    "rate": 10,
                    "capacity": 50,
                },
            },
            retries=3,
            backoff_factor=0.3,
        )
        self.session.headers.update(self.headers)

    def validate(self):
        return self.session.get("/List/My")

    def get_items_from_Listrr(
        self,
        content_type: Literal["Movies", "Shows"],
        content_lists: list[str],
    ) -> list[tuple[str | None, int]]:  # noqa: C901, PLR0912
        """Fetch unique IMDb IDs from Listrr for a given type and list of content."""
        unique_ids: set[tuple[str | None, int]] = set()

        if not content_lists:
            return list()

        @dataclass
        class Item:
            id: str | None
            name: str | None
            firstAirDate: str | None
            releaseDate: str | None
            imDbId: str | None
            tmDbId: int
            tvDbId: int

        @dataclass
        class ResponseData:
            items: list[Item] | None
            pages: int
            count: int

        for list_id in content_lists:
            if not list_id or len(list_id) != 24:
                continue

            page, total_pages = 1, 1

            while page <= total_pages:
                url = f"/List/{content_type}/{list_id}/ReleaseDate/Descending/{page}"
                response = self.session.get(url)
                data = ResponseData(**response.json())

                total_pages = data.pages

                if data.items:
                    for item in data.items:
                        if content_type == "Movies":
                            unique_ids.add((item.imDbId, item.tmDbId))
                        elif content_type == "Shows":
                            unique_ids.add((item.imDbId, item.tvDbId))

                    page += 1

        return list(unique_ids)
