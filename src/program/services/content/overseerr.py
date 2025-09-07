"""Overseerr content module"""

from kink import di
from loguru import logger
from requests.exceptions import ConnectionError, RetryError
from urllib3.exceptions import MaxRetryError, NewConnectionError

from program.apis.overseerr_api import OverseerrAPI
from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.db.db_functions import item_exists_by_any_id


class Overseerr:
    """Content class for overseerr"""

    def __init__(self):
        self.key = "overseerr"
        self.settings = settings_manager.settings.content.overseerr
        self.api = None
        self.initialized = self.validate()
        self.run_once = False
        if not self.initialized:
            return
        logger.success("Overseerr initialized!")

    def validate(self) -> bool:
        if not self.settings.enabled:
            return False
        if self.settings.api_key == "" or len(self.settings.api_key) != 68:
            logger.error("Overseerr api key is not set.")
            return False
        try:
            self.api = di[OverseerrAPI]
            if not (response := self.api.validate()):
                logger.error(
                    f"Overseerr ping failed - Status Code: {response.status_code}, Reason: {response.reason}"
                )
                return False
            return True
        except (ConnectionError, RetryError, MaxRetryError, NewConnectionError):
            logger.error("Overseerr URL is not reachable, or it timed out")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Overseerr validation: {str(e)}")
            return False

    def run(self):
        """Fetch new media from `Overseerr`"""
        if self.settings.use_webhook and self.run_once:
            return

        overseerr_items: list[MediaItem] = self.api.get_media_requests(self.key)

        if self.settings.use_webhook:
            logger.info("Webhook is enabled. Running Overseerr once before switching to webhook only mode")
            self.run_once = True

        if overseerr_items:
            overseerr_items = [
                item for item in overseerr_items
                if not item_exists_by_any_id(
                    imdb_id=item.imdb_id,
                    tvdb_id=item.tvdb_id,
                    tmdb_id=item.tmdb_id
                )]

        logger.info(f"Fetched {len(overseerr_items)} items from overseerr")

        yield overseerr_items