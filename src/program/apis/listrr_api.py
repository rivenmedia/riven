"""Listrr API"""

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

    def get_shows(
        self,
        content_lists: list[str],
    ) -> list[tuple[str | None, str | None]]:
        """Fetch unique show IDs from Listrr for a given list of content."""

        from schemas.listrr import (
            ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIShowDto as APIResponse,
        )

        unique_ids = set[tuple[str | None, str | None]]()

        if not content_lists:
            return list(unique_ids)

        for list_id in content_lists:
            if not list_id or len(list_id) != 24:
                continue

            page, total_pages = 1, 1

            while page <= total_pages:
                url = f"/List/Shows/{list_id}/ReleaseDate/Descending/{page}"

                response = self.session.get(url)

                data = APIResponse.from_dict(
                    response.json(),
                )

                assert data

                total_pages = data.pages or 1

                if data.items:
                    for item in data.items:
                        unique_ids.add((item.im_db_id, str(item.tv_db_id)))

                page += 1

        return list(unique_ids)

    def get_movies(
        self,
        content_lists: list[str],
    ) -> list[tuple[str | None, str | None]]:
        """Fetch unique movie IDs from Listrr for a given list of content."""

        from schemas.listrr import (
            ListrrContractsModelsAPIPagedResponse1ListrrContractsModelsAPIMovieDto as APIResponse,
        )

        unique_ids = set[tuple[str | None, str | None]]()

        if not content_lists:
            return list(unique_ids)

        for list_id in content_lists:
            if not list_id or len(list_id) != 24:
                continue

            page, total_pages = 1, 1

            while page <= total_pages:
                url = f"/List/Movies/{list_id}/ReleaseDate/Descending/{page}"

                response = self.session.get(url)

                data = APIResponse.from_dict(
                    response.json(),
                )

                assert data

                total_pages = data.pages or 1

                if data.items:
                    for item in data.items:
                        unique_ids.add((item.im_db_id, str(item.tm_db_id)))

                page += 1

        return list(unique_ids)
