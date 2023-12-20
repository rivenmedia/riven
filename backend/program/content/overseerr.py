"""Mdblist content module"""
from requests import ConnectTimeout
from utils.settings import settings_manager
from utils.logger import logger
from utils.request import get, ping
from program.media import MediaItemContainer
from program.updaters.trakt import Updater as Trakt


class Overseerr:
    """Content class for overseerr"""

    def __init__(self, media_items: MediaItemContainer):
        self.initialized = False
        self.media_items = media_items
        self.settings = settings_manager.get("overseerr")
        if self.settings.get("api_key") == "" or not self._validate_settings():
            logger.info("Overseerr is not configured and will not be used.")
            return
        self.updater = Trakt()
        self.not_found_ids = []
        self.initialized = True

    def _validate_settings(self):
        try:
            response = ping(
                self.settings.get("url") + "/api/v1/auth/me",
                additional_headers={"X-Api-Key": self.settings.get("api_key")},
                timeout=1,
            )
            return response.ok
        except ConnectTimeout:
            return False

    def run(self):
        """Fetch media from overseerr and add them to media_items attribute
        if they are not already there"""
        items = self._get_items_from_overseerr(10000)
        new_items = [item for item in items if item not in self.media_items]
        container = self.updater.create_items(new_items)
        for item in container:
            item.set_requested_by("Overseerr")
        added_items = self.media_items.extend(container)
        if len(added_items) > 0:
            logger.info("Added %s items", len(added_items))

    def _get_items_from_overseerr(self, amount: int):
        """Fetch media from overseerr"""

        response = get(
            self.settings.get("url") + f"/api/v1/request?take={amount}",
            additional_headers={"X-Api-Key": self.settings.get("api_key")},
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
            self.settings.get("url")
            + f"/api/v1/{overseerr_item.mediaType}/{external_id}?language=en",
            additional_headers={"X-Api-Key": self.settings.get("api_key")},
        )
        if response.is_ok:
            imdb_id = response.data.externalIds.imdbId
            if imdb_id:
                return imdb_id
            self.not_found_ids.append(f"{id_extension}{external_id}")
        title = getattr(response.data, "title", None) or getattr(
            response.data, "originalName", None
        )
        logger.debug("Could not get imdbId for %s", title)
        return None
