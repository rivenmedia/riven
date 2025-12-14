"""Overseerr content module"""

from kink import di
from loguru import logger

from program.apis.overseerr_api import OverseerrAPI
from program.db.db_functions import item_exists_by_any_id
from program.settings import settings_manager
from program.settings.models import OverseerrModel
from program.core.runner import MediaItemGenerator, Runner, RunnerResult
from program.media.item import MediaItem


class Overseerr(Runner[OverseerrModel]):
    """Content class for overseerr"""

    is_content_service = True

    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.content.overseerr

        if not self.enabled:
            return

        self.api = di[OverseerrAPI]
        self.initialized = self.validate()
        self.run_once = False

        if not self.initialized:
            return

        logger.success("Overseerr initialized!")

    def validate(self) -> bool:
        if not self.settings.enabled:
            return False

        if self.settings.api_key == "":
            logger.error("Overseerr API key is not set.")
            return False

        if len(self.settings.api_key) != 68:
            logger.error("Overseerr API key length is invalid.")
            return False

        try:
            return self.api.validate()
        except Exception:
            return False

    def run(self, item: MediaItem) -> MediaItemGenerator:
        """Fetch new media from `Overseerr`"""

        if self.settings.use_webhook and self.run_once:
            return

        overseerr_items = self.api.get_media_requests(
            self.key,
            filter_pending_items=self.run_once,
        )

        if self.settings.use_webhook:
            logger.info(
                "Webhook is enabled. Running Overseerr once before switching to webhook only mode"
            )

            self.run_once = True

        logger.debug(f"Returned {len(overseerr_items)} items from overseerr")

        if overseerr_items:
            overseerr_items = [
                item
                for item in overseerr_items
                if not item_exists_by_any_id(tvdb_id=item.tvdb_id, tmdb_id=item.tmdb_id)
            ]

        logger.info(f"Fetched {len(overseerr_items)} items from overseerr")

        yield RunnerResult(media_items=overseerr_items)
