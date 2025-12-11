"""Mdblist content module"""

from kink import di
from loguru import logger

from program.apis.mdblist_api import MdblistAPI
from program.db.db_functions import item_exists_by_any_id
from program.media.item import MediaItem
from program.settings import settings_manager
from program.settings.models import MdblistModel
from program.core.runner import Runner, RunnerResult


class Mdblist(Runner[MdblistModel]):
    """Content class for mdblist"""

    is_content_service = True

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

    async def run(self, item: MediaItem) -> RunnerResult:
        """Fetch media from mdblist and add them to media_items attribute"""

        media_items = list[MediaItem]()

        try:
            for list_id in self.settings.lists:
                if not list_id:
                    continue

                if isinstance(list_id, int):
                    list_items = self.api.list_items_by_id(list_id)
                else:
                    list_items = self.api.list_items_by_url(list_id)

                assert list_items

                for list_item in list_items:
                    if list_item.mediatype == "movie" and not list_item.id:
                        continue

                    if list_item.mediatype == "show" and not list_item.tvdb_id:
                        continue

                    if list_item.mediatype == "movie" and not item_exists_by_any_id(
                        imdb_id=list_item.imdb_id, tmdb_id=str(list_item.id)
                    ):
                        media_items.append(
                            MediaItem(
                                {
                                    "tmdb_id": list_item.id,
                                    "requested_by": self.key,
                                }
                            )
                        )

                    elif list_item.mediatype == "show" and not item_exists_by_any_id(
                        imdb_id=list_item.imdb_id, tvdb_id=str(list_item.tvdb_id)
                    ):
                        media_items.append(
                            MediaItem(
                                {
                                    "tvdb_id": list_item.tvdb_id,
                                    "requested_by": self.key,
                                }
                            )
                        )

        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                pass
            else:
                logger.error(f"Mdblist error: {e}")

        logger.info(f"Fetched {len(media_items)} new items from Mdblist")

        return RunnerResult(media_items=media_items)

    def _calculate_request_time(self):
        """Calculate requests per 2 minutes based on mdblist limits"""

        limits = self.api.my_limits()

        assert limits and limits.api_requests

        daily_requests = limits.api_requests

        return daily_requests / 24 / 60 * 2
