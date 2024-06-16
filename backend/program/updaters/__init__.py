"""Updater module"""
from typing import Dict

from program.media.item import MediaItem
from program.types import Service
from utils.logger import logger


class Updater:
    def __init__(self, services: Dict[Service, Service]):
        self.key = "updater"
        self.services = services
        self.initialized = self.validate()

    def validate(self) -> bool:
        """Validate that at least one updater service is initialized."""
        if not self.services:
            logger.error("No services provided to Updater.")
            return False
        return any(service.initialized for service in self.services.values())

    def run(self, item: MediaItem):
        if not self.initialized:
            logger.error("Updater is not initialized properly. Cannot run services.")
            return

        for service_cls, service in self.services.items():
            if service.initialized:
                try:
                    yield from service.run(item)
                except StopIteration:
                    logger.debug(f"{service_cls.__name__} finished updating {item.log_string}")
                except Exception as e:
                    logger.error(f"{service_cls.__name__} failed to update {item.log_string}: {e}")