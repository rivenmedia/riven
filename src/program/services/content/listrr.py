"""Listrr content module"""

from kink import di
from loguru import logger

from program.apis.listrr_api import ListrrAPI
from program.db.db_functions import item_exists_by_any_id
from program.media.item import MediaItem
from program.settings import settings_manager
from program.settings.models import ListrrModel
from program.core.runner import MediaItemGenerator, Runner, RunnerResult


class Listrr(Runner[ListrrModel]):
    """Content class for Listrr"""

    is_content_service = True

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.content.listrr

        if not self.enabled:
            return

        self.api = di[ListrrAPI]
        self.initialized = self.validate()

        if not self.initialized:
            return

        logger.success("Listrr initialized!")

    def validate(self) -> bool:
        """Validate Listrr settings."""

        if not self.settings.enabled:
            return False

        if self.settings.api_key == "" or len(self.settings.api_key) != 64:
            logger.error("Listrr api key is not set or invalid.")
            return False

        valid_list_found = False

        for _, content_list in [
            ("movie_lists", self.settings.movie_lists),
            ("show_lists", self.settings.show_lists),
        ]:
            if not content_list:
                continue

            for item in content_list:
                if item == "" or len(item) != 24:
                    return False

            valid_list_found = True

        if not valid_list_found:
            logger.error("Both Movie and Show lists are empty or not set.")
            return False

        try:
            response = self.api.validate()

            if not response.ok:
                logger.error(
                    f"Listrr ping failed - Status Code: {response.status_code}, Reason: {response.reason}",
                )

            return response.ok
        except Exception as e:
            logger.error(f"Listrr ping exception: {e}")
            return False

    def run(self, item: MediaItem) -> MediaItemGenerator:
        """Fetch new media from `Listrr`"""

        try:
            get_movies_response = self.api.get_movies(self.settings.movie_lists)
            get_shows_response = self.api.get_shows(self.settings.show_lists)
        except Exception as e:
            logger.error(f"Failed to fetch items from Listrr: {e}")
            return

        tmdb_ids = [
            tmdb_id
            for (imdb_id, tmdb_id) in get_movies_response
            if not item_exists_by_any_id(imdb_id=imdb_id, tmdb_id=str(tmdb_id))
        ]

        tvdb_ids = [
            tvdb_id
            for (imdb_id, tvdb_id) in get_shows_response
            if not item_exists_by_any_id(imdb_id=imdb_id, tvdb_id=str(tvdb_id))
            if tvdb_id is not None
        ]

        listrr_items = list[MediaItem]()

        for tmdb_id in tmdb_ids:
            listrr_items.append(
                MediaItem(
                    {
                        "tmdb_id": tmdb_id,
                        "requested_by": self.key,
                    }
                )
            )

        for tvdb_id in tvdb_ids:
            listrr_items.append(
                MediaItem(
                    {
                        "tvdb_id": tvdb_id,
                        "requested_by": self.key,
                    }
                )
            )

        logger.info(f"Fetched {len(listrr_items)} new items from Listrr")

        yield RunnerResult(media_items=listrr_items)
