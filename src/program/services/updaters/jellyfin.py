"""Jellyfin Updater module"""
from types import SimpleNamespace
from typing import Generator, Optional, Type

from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    Session,
    create_service_session,
)


class JellyfinRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, response_type=ResponseType.SIMPLE_NAMESPACE, custom_exception: Optional[Type[Exception]] = None, request_logging: bool = False):
        super().__init__(session, response_type=response_type, custom_exception=custom_exception, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, **kwargs) -> ResponseObject:
        return super()._request(method, endpoint, **kwargs)

class JellyfinUpdater:
    def __init__(self):
        self.key = "jellyfin"
        self.initialized = False
        self.settings = settings_manager.settings.updaters.jellyfin
        session = create_service_session()
        self.request_handler = JellyfinRequestHandler(session)
        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.success("Jellyfin Updater initialized!")

    def validate(self) -> bool:
        """Validate Jellyfin library"""
        if not self.settings.enabled:
            return False
        if not self.settings.api_key:
            logger.error("Jellyfin API key is not set!")
            return False
        if not self.settings.url:
            logger.error("Jellyfin URL is not set!")
            return False

        try:
            response = self.request_handler.execute(HttpMethod.GET, f"{self.settings.url}/Users", params={"api_key": self.settings.api_key})
            if response.is_ok:
                self.initialized = True
                return True
        except Exception as e:
            logger.exception(f"Jellyfin exception thrown: {e}")
        return False

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Update Jellyfin library for a single item or a season with its episodes"""
        self.update_item()
        logger.log("JELLYFIN", f"Updated {item.log_string}")
        yield item


    def update_item(self) -> bool:
        """Update the Jellyfin item"""
        try:
            response = self.request_handler.execute(HttpMethod.POST,
                f"{self.settings.url}/Library/Refresh",
                params={"api_key": self.settings.api_key},
            )
            if response.is_ok:
                return True
        except Exception as e:
            logger.error(f"Failed to update Jellyfin item: {e}")
        return False

    # not needed to update, but maybe useful in the future?
    def get_libraries(self) -> list[SimpleNamespace]:
        """Get the libraries from Jellyfin"""
        try:
            response = self.request_handler.execute(HttpMethod.GET,
                f"{self.settings.url}/Library/VirtualFolders",
                params={"api_key": self.settings.api_key},
            )
            if response.is_ok and response.data:
                return response.data
        except Exception as e:
            logger.error(f"Failed to get Jellyfin libraries: {e}")
        return []
