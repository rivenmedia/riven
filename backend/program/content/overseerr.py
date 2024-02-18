"""Mdblist content module"""
from utils.logger import logger
from utils.request import delete, get, ping
from program.settings.manager import settings_manager
from program.media.container import MediaItemContainer
from program.updaters.trakt import get_imdbid_from_tmdb


class Overseerr():
    """Content class for overseerr"""

    def __init__(self):
        self.key = "overseerr"
        self.settings = settings_manager.settings.content.overseerr
        self.headers = {"X-Api-Key": self.settings.api_key}
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.not_found_ids = []
        logger.info("Overseerr initialized!")

    def validate(self) -> bool:
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
            if response.status_code >= 201:
                logger.error(
                    f"Overseerr ping failed - Status Code: {response.status_code}, Reason: {response.reason}"
                )
                return False
            return response.ok
        except Exception:
            logger.error("Overseerr url is not reachable.")
            return False

    def run(self):
        """Fetch new media from `Overseerr`"""
        self.not_found_ids.clear()
        items = self._get_items_from_overseerr(10000)    
        yield from items

    def _get_items_from_overseerr(self, amount: int) -> MediaItemContainer:
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

    def get_imdb_id(self, data) -> str:
        """Get imdbId for item from overseerr"""
        if data.mediaType == "show":
            external_id = data.tvdbId
            data.mediaType = "tv"
            id_extension = "tvdb-"
        else:
            external_id = data.tmdbId
            id_extension = "tmdb-"

        if f"{id_extension}{external_id}" in self.not_found_ids:
            return None
        response = get(
            self.settings.url
            + f"/api/v1/{data.mediaType}/{external_id}?language=en",
            additional_headers=self.headers,
        )
        if not response.is_ok or not hasattr(response.data, "externalIds"):
            logger.debug(
                f"Failed to fetch or no externalIds for {id_extension}{external_id}"
            )
            return None

        title = getattr(response.data, "title", None) or getattr(
            response.data, "originalName", None
        )
        imdb_id = getattr(response.data.externalIds, "imdbId", None)
        if imdb_id:
            return imdb_id

        # Try alternate IDs if IMDb ID is not available
        # alternate_ids = [('tvdbId', get_imdbid_from_tvdb), ('tmdbId', get_imdbid_from_tmdb)]
        alternate_ids = [("tmdbId", get_imdbid_from_tmdb)]
        for id_attr, fetcher in alternate_ids:
            external_id_value = getattr(response.data.externalIds, id_attr, None)
            if external_id_value:
                new_imdb_id = fetcher(external_id_value)
                if new_imdb_id:
                    logger.debug(
                        f"Found imdbId for {title} from {id_attr}: {external_id_value}"
                    )
                    return new_imdb_id

        self.not_found_ids.append(f"{id_extension}{external_id}")
        logger.debug(f"Could not get imdbId for {title}, or match with external id")
        return None

    def delete_request(self, request_id: int) -> bool:
        """Delete request from `Overseerr`"""
        response = delete(
            self.settings.url + f"/api/v1/request/{request_id}",
            additional_headers=self.headers,
        )
        if response.is_ok:
            logger.info(f"Deleted request {request_id} from overseerr")
            return {"success": True, "message": f"Deleted request {request_id}"}