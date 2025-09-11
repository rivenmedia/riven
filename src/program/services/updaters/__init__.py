"""Updater module"""
from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.services.updaters.emby import EmbyUpdater
from program.services.updaters.jellyfin import JellyfinUpdater
from program.services.updaters.plex import PlexUpdater


class Updater:
    def __init__(self):
        self.key = "updater"
        self.services = {
            PlexUpdater: PlexUpdater(),
            JellyfinUpdater: JellyfinUpdater(),
            EmbyUpdater: EmbyUpdater(),
        }
        self.initialized = True

    def validate(self) -> bool:
        """Validate that at least one updater service is initialized."""
        initialized_services = [service for service in self.services.values() if service.initialized]
        return len(initialized_services) > 0

    def run(self, item: MediaItem):
        if not self.initialized:
            logger.error("Updater is not initialized properly.")
            return

        for service_cls, service in self.services.items():
            if service.initialized:
                try:
                    item = next(service.run(item))
                except Exception as e:
                    logger.error(f"{service_cls.__name__} failed to update {item.log_string}: {e}")
        
        for item in get_items_to_update(item):
            item.updated = True
        yield item

def get_items_to_update(item: MediaItem) -> list[MediaItem]:
    if isinstance(item, (Movie, Episode)):
        return [item]
    elif isinstance(item, Show):
        return [e for season in item.seasons for e in season.episodes if e.available_in_vfs]
    elif isinstance(item, Season):
        return [e for e in item.episodes if e.available_in_vfs]