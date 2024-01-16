"""Mdblist content module"""
from typing import Optional
from pydantic import BaseModel
from utils.settings import settings_manager
from utils.logger import logger
from utils.request import get, ping
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt


class ListrrConfig(BaseModel):
    enabled: bool
    movie_lists: Optional[list]
    show_lists: Optional[list]
    api_key: Optional[str]


class Listrr:
    """Content class for Listrr"""

    def __init__(self, media_items: MediaItemContainer):
        self.key = "listrr"
        self.url = "https://listrr.pro/api"
        self.settings = ListrrConfig(**settings_manager.get(f"content.{self.key}"))
        self.headers = {"X-Api-Key": self.settings.api_key}
        self.initialized = self.validate_settings()
        if not self.initialized:
            return
        self.media_items = media_items
        self.updater = Trakt()
        self.unique_ids = set()
        self.not_found_ids = []
        logger.info("Listrr initialized!")

    def validate_settings(self) -> bool:
        if not self.settings.enabled:
            logger.debug("Listrr is set to disabled.")
            return False
        if self.settings.api_key == "" or len(self.settings.api_key) != 64:
            logger.error("Listrr api key is not set.")
            return False
        try:
            response = ping(
                self.settings.url + "/List/My/1",
                additional_headers=self.headers,
                timeout=15,
            )
            return response.ok
        except Exception:
            logger.error("Listrr url is not reachable.")
            return False

    def run(self):
        """Fetch media from Listrr and add them to media_items attribute
        if they are not already there"""
        items = self._get_items_from_Listrr(10000)
        new_items = [item for item in items if item not in self.media_items]
        container = self.updater.create_items(new_items)
        for item in container:
            item.set("requested_by", "Listrr")
        added_items = self.media_items.extend(container)
        length = len(added_items)
        if length >= 1 and length <= 5:
            for item in added_items:
                logger.info("Added %s", item.log_string)
        elif length > 5:
            logger.info("Added %s items", length)

    def _get_items_from_Listrr(self, show_list):
        """Fetch unique IMDb IDs from Listrr"""
        page = 1
        total_pages = 1
        while page <= total_pages:
            response = get(
                self.settings.url + f"/List/Shows/{self.show_lists}/ReleaseDate/Descending/{page}",
                headers=self.headers,
            )
            if response.ok:
                data = response.json()
                total_pages = data['pages']
                for item in data['items']:
                    imdb_id = item.get('imDbId')
                    if imdb_id:
                        self.unique_ids.add(imdb_id)
            else:
                print(f"Failed to fetch data for page {page}")
                break
            page += 1
        return list(self.unique_ids)

