import os
import dill
from pickle import UnpicklingError
from typing import Optional, Iterable
from program.media.item import MediaItem, Episode, Season, Show, ItemId, Movie
from copy import deepcopy

class MediaItemContainer:
    """MediaItemContainer class"""

    def __init__(self, items: Optional[dict[ItemId, MediaItem]] = None):
        if items and not isinstance(items, dict):
            raise TypeError(f"MediaItemContainer items cannot be of type {items.__class__.__name__}, must be dict")
        self.items = items if items is not None else {}

    def __iter__(self):
        for item in self.items.values():
            yield item
            
    def __contains__(self, item):
        return item in self.items

    def __iadd__(self, other):
        if not isinstance(other, MediaItem) and other is not None:
            raise TypeError("Cannot append non-MediaItem to MediaItemContainer")
        if other not in self.items:
            self.items.append(other)
        return self

    def __len__(self):
        """Get length of container"""
        return len(self.items)

    def __getitem__(self, item_id: ItemId):
        return deepcopy(self.items[item_id])

    def get(self, key, default=None):
        return deepcopy(self.items.get(key, default))

    def sort(self, by, reverse):
        """Sort container by given attribute"""
        try:
            self.items.sort(key=lambda item: item.get(by), reverse=reverse)
        except AttributeError:
            pass  # Fixes: 'NoneType' object has no attribute 'get' - caused by Trakt not able to create an item

    def _swap_children_with_ids(self, item_group: list[Season | Episode]) -> list[Season | Episode]:
        for i in range(len(item_group)):
            item = item_group[i]
            if hasattr(item, 'item_id'):
                item_group[i] = item.item_id
                self.items[item.item_id] = item
        return item_group

    @property
    def seasons(self):
        return self.get_items_of_type(Season)
    
    @property
    def episodes(self):
        return self.get_items_of_type(Episode)
    
    @property
    def shows(self):
        return self.get_items_of_type(Show)
    
    @property
    def movies(self):
        return self.get_items_of_type(Movie)

    def upsert(self, item: MediaItem) -> MediaItem:
        """Iterate through the input item and upsert all parents and children."""
        # Use deepcopy so that further modifications made to the input item
        # will not affect the container state
        item = deepcopy(item)

        if isinstance(item, Show):
            for season in item.seasons:
                season.parent = item
                self.items[season.item_id] = season
                for episode in season.episodes:
                    episode.parent = season
                    self.items[episode.item_id] = episode
        if isinstance(item, Season):
            # update children
            for episode in item.episodes:
                episode.parent = item
                self.items[episode.item_id] = episode
            # Ensure the parent Show is updated in the container
            container_show: Show = self.items[item.item_id.parent_id]
            parent_index = container_show.get_season_index_by_id(item.item_id)
            if parent_index is not None:
                container_show.seasons[parent_index] = item
        elif isinstance(item, Episode):
            # Ensure the parent Season is updated in the container            
            container_season: Season = self.items[item.item_id.parent_id]
            parent_index = container_season.get_episode_index_by_id(item.item_id)
            if parent_index is not None:
                container_season.episodes[parent_index] = item

        self.items[item.item_id] = item

    def remove(self, item):
        """Remove item from container"""
        if item.item_id in self.items:
            self.items.remove(item)

    def count(self, state) -> int:
        """Count items with given state in container"""
        return len(self.get_items_with_state(state))

    def get_items_with_state(self, state):
        """Get items with the specified state"""
        return {
            item_id: self[item_id]
            for item_id, item in self.items.items()
            if item.state == state
        }

    def get_items_of_type(self, item_type: MediaItem | Iterable[MediaItem]):
        """Get items with one or more states"""
        return {
            item_id: self[item_id]
            for item_id, item in self.items.items()
            if isinstance(item, item_type)
        }

    def save(self, filename):
        """Save container to file"""
        with open(filename, "wb") as file:
            dill.dump(self.items, file)

    def load(self, filename):
        """Load container from file"""
        try:
            with open(filename, "rb") as file:
                self.items = dill.load(file)
        except FileNotFoundError:
            self.items = {}
        except (EOFError, UnpicklingError):
            os.remove(filename)
            self.items = {}
