from loguru import logger
from typing import Any, Literal, Self
from pydantic import BaseModel, StrictInt, StrictStr
from program.utils.request import SmartSession


class MdblistAPIError(Exception):
    """Base exception for MdblistAPI related errors"""

    def __init__(self, error: str) -> None:
        self.error = error


class MdblistAPIErrorResponse(BaseModel):
    error: StrictStr


class MdblistAPI:
    """Handles Mdblist API communication"""

    BASE_URL = "https://api.mdblist.com"

    def __init__(self, api_key: str):
        self.session = SmartSession(
            base_url=self.BASE_URL,
            rate_limits={
                "api.mdblist.com": {
                    # 60 calls per minute
                    "rate": 1,
                    "capacity": 60,
                }
            },
            retries=3,
            backoff_factor=0.3,
        )

        self.common_query_params = {"apikey": api_key}

    def validate(self):
        try:
            response = self.session.get(
                "/user",
                params=self.common_query_params,
            )

            if not response.ok:
                error_response = MdblistAPIErrorResponse.model_validate(response.json())

                raise MdblistAPIError(error_response.error)

            return True
        except MdblistAPIError as e:
            logger.error(f"Mdblist error: {e.error}")

            return False

    def my_limits(self):
        """Wrapper for mdblist api method 'My limits'"""

        from schemas.mdblist import GetMyLimits200Response

        response = self.session.get(
            "/user",
            params=self.common_query_params,
        )

        return GetMyLimits200Response.from_dict(response.json())

    def list_items_by_id(self, list_id: int):
        """Wrapper for mdblist api method 'List items'"""

        from schemas.mdblist import (
            GetListItemsByName200Response,
        )

        response = self.session.get(
            f"/lists/{str(list_id)}/items",
            params=self.common_query_params,
        )

        if not response.ok:
            return

        data = GetListItemsByName200Response.from_dict(response.json())

        assert data and data.movies and data.shows

        return [*data.movies, *data.shows]

    def list_items_by_url(self, url: str):
        """Gets list items from a given mdblist url"""

        class ListItems(BaseModel):
            class ListItem(BaseModel):
                id: StrictInt
                rank: StrictInt
                adult: Literal[0, 1]
                title: StrictStr
                imdb_id: StrictStr | None = None
                tvdbid: StrictInt | None = None
                mediatype: Literal["movie", "show"]
                release_year: StrictInt

                @property
                def tvdb_id(self) -> StrictInt | None:
                    return self.tvdbid

            items: list[ListItem]

        url = url if url.endswith("/") else f"{url}/"
        url = url if url.endswith("json/") else f"{url}json/"

        response = self.session.get(
            url,
            params=self.common_query_params,
        )

        return ListItems(items=response.json()).items
