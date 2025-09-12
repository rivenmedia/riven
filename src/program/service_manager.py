"""Process-local service manager for initializing and validating services once.

This module provides a singleton `service_manager` used by both the main app
and Dramatiq workers. It constructs core processing services, wires DI
dependencies, validates them, and exposes a consistent registry for
`global_services` and internal access.
"""

from __future__ import annotations

from threading import Lock
from typing import Any, Dict, Optional, Type, TypeVar

from kink import di
from loguru import logger

from program.apis import bootstrap_apis
from program.services.downloaders import Downloader
from program.services.indexers import CompositeIndexer, TMDBIndexer, TVDBIndexer
from program.services.libraries import SymlinkLibrary
from program.services.post_processing import PostProcessing
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.settings.manager import settings_manager
from program.symlink import Symlinker
from program.utils.logging import setup_logger

Service = TypeVar("Service")

setup_logger("DEBUG" if settings_manager.settings.debug else "INFO")

class ServiceManager:
    """Initializes DI and core services exactly once per process."""

    def __init__(self) -> None:
        self._init_lock = Lock()
        self._initialized = False
        self._services: Dict[Type, object] = {}

    def initialize(self) -> None:
        """Initialize core services (excluding SymlinkLibrary which is lazy-loaded)."""
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            # Ensure external APIs and DI set up
            try:
                bootstrap_apis()
            except Exception as e:
                logger.debug(f"bootstrap_apis warning: {e}")

            # Wire DI for indexers
            try:
                _ = di[TMDBIndexer]
            except Exception:
                di[TMDBIndexer] = TMDBIndexer()
            try:
                _ = di[TVDBIndexer]
            except Exception:
                di[TVDBIndexer] = TVDBIndexer()

            # Core services (SymlinkLibrary is excluded - will be lazy-loaded)
            services: Dict[Type, object] = {
                CompositeIndexer: CompositeIndexer(),
                Scraping: Scraping(),
                Symlinker: Symlinker(),
                Updater: Updater(),
                Downloader: Downloader(),
                PostProcessing: PostProcessing(),
            }

            for cls, instance in services.items():
                # All services are expected to have an 'initialized' attribute
                valid = bool(getattr(instance, "initialized", False))
                if not valid:
                    logger.error(f"Service {cls.__name__} failed validation (initialized=False)")
                self._services[cls] = instance

            self._initialized = True
            logger.debug("ServiceManager initialized core services")

    @property
    def services(self) -> Dict[Type, object]:
        """Backward-compatible property for code that accessed `.services`."""
        return self.get_services()

    def get_services(self) -> Dict[Type, object]:
        """Get all service instances."""
        self.initialize()
        return self._services

    def get_service(self, service_class: Type[Service]) -> Optional[Service]:
        """Get a service instance by its class type.
        
        Args:
            service_class: The service class to retrieve
            
        Returns:
            The service instance or None if not found
        """
        self.initialize()
        
        # Special handling for SymlinkLibrary - lazy load it
        if service_class == SymlinkLibrary and service_class not in self._services:
            self._add_symlink_library()
            
        return self._services.get(service_class)

    def get_service_by_name(self, name: str) -> Optional[Service]:
        """Get a service instance by its name.
        
        Args:
            name: The service name (e.g., "CompositeIndexer", "Scraping")
            
        Returns:
            The service instance or None if not found
        """
        self.initialize()

        service_name_to_class = {
            "CompositeIndexer": CompositeIndexer,
            "Scraping": Scraping,
            "Downloader": Downloader,
            "Symlinker": Symlinker,
            "Updater": Updater,
            "PostProcessing": PostProcessing,
            "SymlinkLibrary": SymlinkLibrary,
        }
        
        service_class = service_name_to_class.get(name)
        if not service_class:
            logger.error(f"Unknown service name: {name}")
            return None
            
        return self.get_service(service_class)

    def set_service(self, service_class: Type[Service], instance: Service) -> None:
        """Set a service instance by its class type.
        
        Args:
            service_class: The service class type
            instance: The service instance to store
        """
        self._services[service_class] = instance
        logger.debug(f"Set service {service_class.__name__}")

    def remove_service(self, service_class: Type[Service]) -> Optional[Service]:
        """Remove a service instance by its class type.
        
        Args:
            service_class: The service class to remove
            
        Returns:
            The removed service instance or None if not found
        """
        instance = self._services.pop(service_class, None)
        if instance:
            logger.debug(f"Removed service {service_class.__name__}")
        return instance

    def has_service(self, service_class: Type[Service]) -> bool:
        """Check if a service instance exists for the given class type.
        
        Args:
            service_class: The service class to check
            
        Returns:
            True if the service exists, False otherwise
        """
        return service_class in self._services

    def get_all_services(self) -> Dict[Type, object]:
        """Get all service instances.
        
        Returns:
            Dictionary mapping service classes to their instances
        """
        self.initialize()
        return dict(self._services)

    def _add_symlink_library(self) -> None:
        """Lazy-load SymlinkLibrary service when requested."""
        try:
            instance = SymlinkLibrary()
            if instance.initialized:
                self._services[SymlinkLibrary] = instance
                logger.debug("Lazy-loaded SymlinkLibrary service")
            else:
                raise RuntimeError("SymlinkLibrary failed validation (initialized=False)")
        except Exception as e:
            logger.error(f"Failed to lazy-load SymlinkLibrary: {e}")
            raise


service_manager = ServiceManager()
