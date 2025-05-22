"""Base indexer module"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Generator, Optional, Union

from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager


class BaseIndexer(ABC):
    """Base class for all indexers"""
    
    def __init__(self):
        self.key = self.__class__.__name__.lower()
        self.initialized = True
        self.settings = settings_manager.settings.indexer
        self.failed_ids = set()
        
    @staticmethod
    def copy_attributes(source, target):
        """Copy attributes from source to target."""
        attributes = ["file", "folder", "update_folder", "symlinked", "is_anime", "symlink_path", "subtitles", 
                      "requested_by", "requested_at", "overseerr_id", "active_stream", "requested_id", "streams"]
        for attr in attributes:
            target.set(attr, getattr(source, attr, None))

    def copy_items(self, itema: MediaItem, itemb: MediaItem):
        """Copy attributes from itema to itemb recursively."""
        is_anime = itema.is_anime or itemb.is_anime
        if itema.type == "mediaitem" and itemb.type == "show":
            itema.seasons = itemb.seasons
        if itemb.type == "show" and itema.type != "movie":
            for seasona in itema.seasons:
                for seasonb in itemb.seasons:
                    if seasona.number == seasonb.number:  # Check if seasons match
                        for episodea in seasona.episodes:
                            for episodeb in seasonb.episodes:
                                if episodea.number == episodeb.number:  # Check if episodes match
                                    self.copy_attributes(episodea, episodeb)
                        seasonb.set("is_anime", is_anime)
            itemb.set("is_anime", is_anime)
        elif itemb.type == "movie":
            self.copy_attributes(itema, itemb)
            itemb.set("is_anime", is_anime)
        else:
            logger.error(f"Item types {itema.type} and {itemb.type} do not match cant copy metadata")
        return itemb
        
    @abstractmethod
    def run(self, in_item: MediaItem, log_msg: bool = True) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Run the indexer for the given item. Must be implemented by subclasses."""
        pass
        
    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        if not item.indexed_at or not item.title:
            return True

        settings = settings_manager.settings.indexer

        try:
            interval = timedelta(seconds=settings.update_interval)
            return datetime.now() - item.indexed_at > interval
        except Exception:
            logger.error(f"Failed to parse date: {item.indexed_at} with format: {interval}")
            return False
