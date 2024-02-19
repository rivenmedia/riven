import os
import threading
import dill
from pickle import UnpicklingError
from typing import Optional
from program.media.item import MediaItem, Episode, Season, Show, ItemId
from copy import deepcopy

class MediaItemContainer:
    """MediaItemContainer class"""

    def __init__(self, items: Optional[dict[ItemId, MediaItem]] = None):
        self.items = items if items is not None else {}

    def __iter__(self):
        for item in self.items.values():
            yield item

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

    def append(self, item: MediaItem) -> MediaItem:
        """Iterate through all child items, swap direct references with ItemIDs, then add
        each item in tree to the items dict flat so they can be directly referenced later"""
        if isinstance(item, Show):
            for season in item.seasons:
                season.parent = item
                self.items[season.item_id] = season
                for episode in season.episodes:
                    episode.parent = season
                    self.items[episode.item_id] = episode
        if isinstance(item, Season):
            for episode in item.episodes:
                episode.parent = item
                self.items[episode.item_id] = episode
        self.items[item.item_id] = item
        return self[item.item_id]

    def remove(self, item):
        """Remove item from container"""
        if item.item_id in self.items:
            self.items.remove(item)

    def count(self, state) -> int:
        """Count items with given state in container"""
        return len(self.get_items_with_state(state))

    def get_items_with_state(self, state):
        """Get items that need to be updated"""
        return MediaItemContainer({
            item_id: self[item_id]
            for item_id, item in self.items.items()
            if item.state == state
        })

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
            self.items = []
        except (EOFError, UnpicklingError):
            os.remove(filename)
            self.items = []
