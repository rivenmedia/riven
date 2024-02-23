import os
from copy import deepcopy
import dill
from pickle import UnpicklingError
from typing import Generator

from program.media.item import MediaItem, Episode, Season, Show, ItemId, Movie
from program.media.state import States
from utils.logger import logger

class MediaItemContainer:
    """MediaItemContainer class"""

    def __init__(self):
        self._items = {}
        self._shows = {}
        self._seasons = {}
        self._episodes = {}
        self._movies = {}

    def __iter__(self) -> Generator[MediaItem, None, None]:
        for item in self._items.values():
            yield item
            
    def __contains__(self, item) -> bool:
        return item in self._items

    def __len__(self) -> int:
        """Get length of container"""
        return len(self._items)

    def __getitem__(self, item_id: ItemId) -> MediaItem:
        return deepcopy(self._items[item_id])

    def get(self, key, default=None) -> MediaItem:
        return deepcopy(self._items.get(key, default))

    @property
    def seasons(self) -> dict[ItemId, Season]:
        return deepcopy(self._seasons)
        
    @property
    def episodes(self) -> dict[ItemId, Episode]:
        return deepcopy(self._episodes)
    
    @property
    def shows(self) -> dict[ItemId, Show]:
        return deepcopy(self._shows)
    
    @property
    def movies(self) -> dict[ItemId, Movie]:
        return deepcopy(self._movies)

    def upsert(self, item: MediaItem) -> None:
        """Iterate through the input item and upsert all parents and children."""
        # Use deepcopy so that further modifications made to the input item
        # will not affect the container state
        item = deepcopy(item)
        self._items[item.item_id] = item
        detatched = item.item_id.parent_id is None or item.parent is None
        if isinstance(item, (Season, Episode)) and detatched:
            logger.error(
                "%s item %s is detatched and not associated with a parent, and thus" +
                " it cannot be upserted into the database", 
                item.__class__.name, item.log_string
            )
            raise ValueError("Item detached from parent")
        if isinstance(item, Show):
            self._shows[item.item_id] = item
            for season in item.seasons:
                season.parent = item
                self._items[season.item_id] = season
                self._seasons[season.item_id] = season
                for episode in season.episodes:
                    episode.parent = season
                    self._items[episode.item_id] = episode
                    self._episodes[episode.item_id] = episode
        if isinstance(item, Season):
            self._seasons[item.item_id] = item
            # update children
            for episode in item.episodes:
                episode.parent = item
                self._items[episode.item_id] = episode
                self._episodes[episode.item_id] = episode
            # Ensure the parent Show is updated in the container
            container_show: Show = self._items[item.item_id.parent_id]
            parent_index = container_show.get_season_index_by_id(item.item_id)
            if parent_index is not None:
                container_show.seasons[parent_index] = item
        elif isinstance(item, Episode):
            self._episodes[item.item_id] = item
            # Ensure the parent Season is updated in the container            
            container_season: Season = self._items[item.item_id.parent_id]
            parent_index = container_season.get_episode_index_by_id(item.item_id)
            if parent_index is not None:
                container_season.episodes[parent_index] = item
        elif isinstance(item, Movie):
            self._movies[item.item_id] = item

    def remove(self, item) -> None:
        """Remove item from container"""
        if item.item_id in self._items:
            del self._items[item.item_id]

    def count(self, state) -> int:
        """Count items with given state in container"""
        return len(self.get_items_with_state(state))

    def get_items_with_state(self, state) -> dict[ItemId, MediaItem]:
        """Get items with the specified state"""
        return {
            item_id: self[item_id]
            for item_id, item in self._items.items()
            if item.state == state
        }
    
    def get_incomplete_items(self) -> dict[ItemId, MediaItem]:
        """Get items with the specified state"""
        return {
            item_id: self[item_id]
            for item_id, item in self._items.items()
            if item.state not in (States.Completed, States.PartiallyCompleted)
        }

    def save(self, filename) -> None:
        """Save container to file"""
        with open(filename, "wb") as file:
            dill.dump(self._items, file)

    def load(self, filename) -> None:
        """Load container from file"""
        try:
            with open(filename, "rb") as file:
                self._items = dill.load(file)
        except FileNotFoundError:
            self._items = {}
        except (EOFError, UnpicklingError):
            os.remove(filename)
            self._items = {}
