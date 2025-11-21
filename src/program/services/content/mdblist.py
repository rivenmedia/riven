"""Mdblist content module"""

from kink import di
from loguru import logger

from program.apis.mdblist_api import MdblistAPI
from program.db.db_functions import item_exists_by_any_id
from program.media.item import MediaItem
from program.settings import settings_manager
from program.core.content_service import ContentService
from program.settings.models import MdblistModel
from program.core.runner import MediaItemGenerator, RunnerResult


class Mdblist(ContentService[MdblistModel]):
    """Content class for mdblist"""

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.content.mdblist

        if not self.enabled:
            return

        self.api = di[MdblistAPI]
        self.initialized = self.validate()

        if not self.initialized:
            return

        self.requests_per_2_minutes = self._calculate_request_time()

        logger.success("mdblist initialized")

    def validate(self):
        if not self.settings.enabled:
            return False

        if self.settings.api_key == "" or len(self.settings.api_key) != 25:
            logger.error("Mdblist api key is not set.")
            return False

        if not self.settings.lists:
            logger.error("Mdblist is enabled, but you haven't added any lists.")
            return False

        return self.api.validate()

    def run(self) -> MediaItemGenerator:
        """Fetch media from mdblist and add them to media_items attribute"""

        items_to_yield: list[MediaItem] = []

        try:
            for list_id in self.settings.lists:
                if not list_id:
                    continue

                if isinstance(list_id, int):
                    items = self.api.list_items_by_id(list_id)
                else:
                    items = self.api.list_items_by_url(list_id)

                assert items

                for item in items:
                    if item.mediatype == "movie" and not item.id:
                        continue

                    if item.mediatype == "show" and not item.tvdb_id:
                        continue

                    if item.mediatype == "movie" and not item_exists_by_any_id(
                        imdb_id=item.imdb_id, tmdb_id=str(item.id)
                    ):
                        items_to_yield.append(
                            MediaItem(
                                {
                                    "tmdb_id": item.id,
                                    "requested_by": self.key,
                                }
                            )
                        )

                    elif item.mediatype == "show" and not item_exists_by_any_id(
                        imdb_id=item.imdb_id, tvdb_id=str(item.tvdb_id)
                    ):
                        items_to_yield.append(
                            MediaItem(
                                {
                                    "tvdb_id": item.tvdb_id,
                                    "requested_by": self.key,
                                }
                            )
                        )

        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                pass
            else:
                logger.error(f"Mdblist error: {e}")

        logger.info(f"Fetched {len(items_to_yield)} new items from Mdblist")

        yield RunnerResult(media_items=items_to_yield)

    def _calculate_request_time(self):
        """Calculate requests per 2 minutes based on mdblist limits"""

        limits = self.api.my_limits()

        assert limits and limits.api_requests

        daily_requests = limits.api_requests

        return daily_requests / 24 / 60 * 2
