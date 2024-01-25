"""Mdblist content module"""
from typing import Optional
from pydantic import BaseModel
from utils.settings import settings_manager
from utils.logger import logger
from utils.request import get, ping
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt, get_imdbid_from_tmdb, get_imdbid_from_tvdb


class OverseerrConfig(BaseModel):
    enabled: bool
    url: Optional[str]
    api_key: Optional[str]


class Overseerr:
    """Content class for overseerr"""

    def __init__(self, media_items: MediaItemContainer):
        self.key = "overseerr"
        self.settings = OverseerrConfig(**settings_manager.get(f"content.{self.key}"))
        self.headers = {"X-Api-Key": self.settings.api_key}
        self.initialized = self.validate_settings()
        if not self.initialized:
            return
        self.media_items = media_items
        self.updater = Trakt()
        self.not_found_ids = []
        logger.info("Overseerr initialized!")

    def validate_settings(self) -> bool:
        if not self.settings.enabled:
            logger.debug("Overseerr is set to disabled.")
            return False
        if self.settings.api_key == "" or len(self.settings.api_key) != 68:
            logger.error("Overseerr api key is not set.")
            return False
        try:
            response = ping(
                self.settings.url + "/api/v1/auth/me",
                additional_headers=self.headers,
                timeout=15,
            )
            return response.ok
        except Exception:
            logger.error("Overseerr url is not reachable.")
            return False

    def run(self):
        """Fetch media from overseerr and add them to media_items attribute
        if they are not already there"""
        items = self._get_items_from_overseerr(10000)
        new_items = [item for item in items if item not in self.media_items] or []
        container = self.updater.create_items(new_items)
        for item in container:
            item.set("requested_by", "Overseerr")
        added_items = self.media_items.extend(container)
        length = len(added_items)
        if length >= 1 and length <= 5:
            for item in added_items:
                logger.info("Added %s", item.log_string)
        elif length > 5:
            logger.info("Added %s items", length)

    def _get_items_from_overseerr(self, amount: int):
        """Fetch media from overseerr"""
        response = get(
            self.settings.url + f"/api/v1/request?take={amount}",
            additional_headers=self.headers,
        )
        ids = []
        if response.is_ok:
            for item in response.data.results:
                if not item.media.imdbId:
                    imdb_id = self.get_imdb_id(item.media)
                    if imdb_id:
                        ids.append(imdb_id)
                else:
                    ids.append(item.media.imdbId)
        return ids

    def get_imdb_id(self, overseerr_item):
        """Get imdbId for item from overseerr"""
        if overseerr_item.mediaType == "show":
            external_id = overseerr_item.tvdbId
            overseerr_item.mediaType = "tv"
            id_extension = "tvdb-"
        else:
            external_id = overseerr_item.tmdbId
            id_extension = "tmdb-"

        if f"{id_extension}{external_id}" in self.not_found_ids:
            return None
        response = get(
            self.settings.url + f"/api/v1/{overseerr_item.mediaType}/{external_id}?language=en",
            additional_headers=self.headers,
        )
        if not response.is_ok or not hasattr(response.data, "externalIds"):
            logger.debug(f"Failed to fetch or no externalIds for {id_extension}{external_id}")
            return None

        title = getattr(response.data, "title", None) or getattr(response.data, "originalName", None)

        # Try to get IMDb ID directly
        imdb_id = getattr(response.data.externalIds, 'imdbId', None)
        if imdb_id:
            return imdb_id

        # Try alternate IDs if IMDb ID is not available
        alternate_ids = [('tvdbId', get_imdbid_from_tvdb), ('tmdbId', get_imdbid_from_tmdb)]
        for id_attr, fetcher in alternate_ids:
            external_id_value = getattr(response.data.externalIds, id_attr, None)
            if external_id_value:
                new_imdb_id = fetcher(external_id_value)
                if new_imdb_id:
                    logger.debug(f"Found imdbId for {title} from {id_attr}: {external_id_value}")
                    return new_imdb_id

        # Log and append to not found if IMDb ID is still not found
        self.not_found_ids.append(f"{id_extension}{external_id}")
        logger.debug(f"Could not get imdbId for {title}, or match with external id")
        return None
