"""Mdblist content module"""
from utils.settings import settings_manager
from utils.logger import logger
from utils.request import get
from program.media import MediaItemContainer
from program.updaters.trakt import Updater as Trakt


class Content:
    """Content class for mdblist"""

    def __init__(
        self,
    ):
        self.settings = settings_manager.get("content_overseerr")
        self.updater = Trakt()
        self.not_found_ids = []

    def update_items(self, media_items: MediaItemContainer):
        """Fetch media from overseerr and add them to media_items attribute
        if they are not already there"""
        logger.info("Getting items...")
        items = self._get_items_from_overseerr(1000)
        container = self.updater.create_items(items)
        added_items = media_items.extend(container)
        if len(added_items) > 0:
            logger.info("Added %s items", len(added_items))
        logger.info("Done!")

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
