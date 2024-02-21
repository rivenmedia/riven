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

    def __iter__(self) -> MediaItem:
        for item in self.items.values():
            yield item
            
    def __contains__(self, item) -> bool:
        return item in self.items

    def __len__(self) -> int:
        """Get length of container"""
        return len(self.items)

    def __getitem__(self, item_id: ItemId) -> MediaItem:
        return deepcopy(self.items[item_id])

    def get(self, key, default=None) -> MediaItem:
        return deepcopy(self.items.get(key, default))

    def sort(self, by, reverse) -> None:
        """Sort container by given attribute"""
        try:
            self.items.sort(key=lambda item: item.get(by), reverse=reverse)
        except AttributeError:
            pass  # Fixes: 'NoneType' object has no attribute 'get' - caused by Trakt not able to create an item

    @property
    def seasons(self) -> dict[ItemId, Season]:
        return self.get_items_of_type(Season)
    
    @property
    def episodes(self) -> dict[ItemId, Episode]:
        return self.get_items_of_type(Episode)
    
    @property
    def shows(self) -> dict[ItemId, Show]:
        return self.get_items_of_type(Show)
    
    @property
    def movies(self) -> dict[ItemId, Movie]:
        return self.get_items_of_type(Movie)

    def upsert(self, item: MediaItem) -> None:
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

    def remove(self, item) -> None:
        """Remove item from container"""
        if item.item_id in self.items:
            del self.items[item.item_id]

    def count(self, state) -> int:
        """Count items with given state in container"""
        return len(self.get_items_with_state(state))

    def get_items_with_state(self, state) -> dict[ItemId, MediaItem]:
        """Get items with the specified state"""
        return {
            item_id: self[item_id]
            for item_id, item in self.items.items()
            if item.state == state
        }

    def get_items_of_type(self, item_type: MediaItem | Iterable[MediaItem]) -> dict[ItemId, MediaItem]:
        """Get items with one or more states"""
        return {
            item_id: self[item_id]
            for item_id, item in self.items.items()
            if isinstance(item, item_type)
        }

    def save(self, filename) -> None:
        """Save container to file"""
        with open(filename, "wb") as file:
            dill.dump(self.items, file)

    def load(self, filename) -> None:
        """Load container from file"""
        try:
            with open(filename, "rb") as file:
                self.items = dill.load(file)
        except FileNotFoundError:
            self.items = {}
        except (EOFError, UnpicklingError):
            os.remove(filename)
            self.items = {}
