from loguru import logger
from requests.exceptions import HTTPError

from program.apis.trakt_api import TraktAPI
from program.media.item import MediaItem
from program.utils.request import get, ping, create_service_session


class ListrrAPI:
    """Handles Listrr API communication"""

    def __init__(self, api_key: str):
        self.BASE_URL = "https://listrr.pro"
        self.api_key = api_key
        self.headers = {"X-Api-Key": self.api_key}
        self.session = create_service_session()
        self.session.headers.update(self.headers)
        self.trakt_api = TraktAPI(rate_limit=False)

    def validate(self):
        return ping(session=self.session, url=self.BASE_URL)

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
                    url = f"{self.BASE_URL}/api/List/{content_type}/{list_id}/ReleaseDate/Descending/{page}"
                    response = get(session=self.session, url=url).response
                    data = response.json()
                    total_pages = data.get("pages", 1)
                    for item in data.get("items", []):
                        imdb_id = item.get("imDbId")
                        if imdb_id:
                            unique_ids.add(imdb_id)
                        elif content_type == "Movies" and item.get("tmDbId"):
                            imdb_id = self.trakt_api.get_imdbid_from_tmdb(item["tmDbId"])
                            if imdb_id:
                                unique_ids.add(imdb_id)
                except HTTPError as e:
                    if e.response.status_code in [400, 404, 429, 500]:
                        break
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                    break
                page += 1
        return list(unique_ids)
