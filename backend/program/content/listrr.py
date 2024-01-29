"""Mdblist content module"""
from time import time
from typing import Optional
from pydantic import BaseModel
from utils.settings import settings_manager
from utils.logger import logger
from utils.request import get, ping
from requests.exceptions import HTTPError
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt, get_imdbid_from_tmdb, get_imdbid_from_tvdb


class ListrrConfig(BaseModel):
    enabled: bool
    movie_lists: Optional[list]
    show_lists: Optional[list]
    api_key: Optional[str]
    update_interval: int  # in seconds


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
        self.next_run_time = 0
        logger.info("Listrr initialized!")

    def validate_settings(self) -> bool:
        """Validate Listrr settings."""
        if not self.settings.enabled:
            logger.debug("Listrr is set to disabled.")
            return False
        if self.settings.api_key == "" or len(self.settings.api_key) != 64:
            logger.error("Listrr api key is not set or invalid.")
            return False
        valid_list_found = False
        for list_name, content_list in [('movie_lists', self.settings.movie_lists), 
                                        ('show_lists', self.settings.show_lists)]:
            if content_list is None or not any(content_list):
                continue
            for item in content_list:
                if item == "" or len(item) != 24:
                    return False
            valid_list_found = True
        if not valid_list_found:
            logger.error("Both Movie and Show lists are empty or not set.")
            return False
        try:
            response = ping("https://listrr.pro/", additional_headers=self.headers)
            if not response.ok:
                logger.error(f"Listrr ping failed - Status Code: {response.status_code}, Reason: {response.reason}")
            return response.ok
        except Exception as e:
            logger.error(f"Listrr ping exception: {e}")
            return False

    def run(self):
        """Fetch media from Listrr and add them to media_items attribute."""
        if time() < self.next_run_time:
            return
        self.next_run_time = time() + self.settings.update_interval
        movie_items = self._get_items_from_Listrr("Movies", self.settings.movie_lists)
        show_items = self._get_items_from_Listrr("Shows", self.settings.show_lists)
        items = list(set(movie_items + show_items))
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

    def _get_items_from_Listrr(self, content_type, content_lists):
        """Fetch unique IMDb IDs from Listrr for a given type and list of content."""
        unique_ids = set()
        for list_id in content_lists:
            page = 1
            total_pages = 1
            while page <= total_pages:
                if list_id == "":
                    break
                try:
                    response = get(
                        self.url + f"/List/{content_type}/{list_id}/ReleaseDate/Descending/{page}",
                        additional_headers=self.headers,
                    )
                    if response.is_ok:
                        total_pages = response.data.pages
                        for item in response.data.items:
                            imdb_id = item.imDbId
                            if imdb_id:
                                unique_ids.add(imdb_id)
                            # elif content_type == "Shows" and item.tvDbId:
                            #     imdb_id = get_imdbid_from_tvdb(item.tvDbId)
                            #     if imdb_id:
                            #         unique_ids.add(imdb_id)
                            if not imdb_id and content_type == "Movies" and item.tmDbId:
                                imdb_id = get_imdbid_from_tmdb(item.tmDbId)
                                if imdb_id:
                                    unique_ids.add(imdb_id)
                            else:
                                break
                except HTTPError as e:
                    if e.response.status_code in [400, 404, 429, 500]:
                        break
                except Exception as e:
                    logger.error(f"An error occurred: {e}")
                    break
                page += 1
        return list(unique_ids)
