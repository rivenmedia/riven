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
        items_to_update = []

        if item.type in ["movie", "episode"]:
            items_to_update = [item]
        elif item.type == "show":
            for season in item.seasons:
                items_to_update += [e for e in season.episodes if e.symlinked and e.update_folder != "updated"]
        elif item.type == "season":
            items_to_update = [e for e in item.episodes if e.symlinked and e.update_folder != "updated"]

        if not items_to_update:
            logger.debug(f"No items to update for {item.log_string}")
            return

        updated = False
        updated_episodes = []

        for item_to_update in items_to_update:
            if self.update_item(item_to_update):
                updated_episodes.append(item_to_update)
                updated = True

        if updated:
            if item.type in ["show", "season"]:
                if len(updated_episodes) == len(items_to_update):
                    logger.log("JELLYFIN", f"Updated all episodes for {item.log_string}")
                else:
                    updated_episodes_log = ", ".join([str(ep.number) for ep in updated_episodes])
                    logger.log("JELLYFIN", f"Updated episodes {updated_episodes_log} in {item.log_string}")
            else:
                logger.log("JELLYFIN", f"Updated {item.log_string}")

        yield item


    def update_item(self, item: MediaItem) -> bool:
        """Update the Jellyfin item"""
        if item.symlinked and item.update_folder != "updated" and item.symlink_path:
            try:
                response = self.request_handler.execute(HttpMethod.POST,
                    f"{self.settings.url}/Library/Media/Updated",
                    json={"Updates": [{"Path": item.symlink_path, "UpdateType": "Created"}]},
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
