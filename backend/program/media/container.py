import os
import threading
import dill
from pickle import UnpicklingError
from typing import List, Optional
from program.media.item import MediaItem


class MediaItemContainer:
    """MediaItemContainer class"""

    def __init__(self, items: Optional[List[MediaItem]] = None):
        self.items = items if items is not None else {}
        self.lock = threading.Lock()

    def __iter__(self):
        for item in self.items.values():
            yield item

    def __iadd__(self, other):
        if not isinstance(other, MediaItem) and other is not None:
            raise TypeError("Cannot append non-MediaItem to MediaItemContainer")
        if other not in self.items:
            self.items.append(other)
        return self

    def sort(self, by, reverse):
        """Sort container by given attribute"""
        try:
            self.items.sort(key=lambda item: item.get(by), reverse=reverse)
        except AttributeError:
            pass  # Fixes: 'NoneType' object has no attribute 'get' - caused by Trakt not able to create an item

    def __len__(self):
        """Get length of container"""
        return len(self.items)

    def append(self, item) -> bool:
        """Append item to container"""
        with self.lock:
            self.items[item.itemid] = item
            self.sort("requested_at", True)

    def get_item(self, attr, value) -> "MediaItemContainer":
        """Get items that match given items"""
        return next((item for item in self.items if getattr(item, attr) == value), None)

    def extend(self, items) -> "MediaItemContainer":
        """Extend container with items"""
        with self.lock:
            added_items = MediaItemContainer()
            for media_item in items:
                if media_item.itemid not in self.items:
                    self.items.append(media_item)
                    added_items.append(media_item)
            self.sort("requested_at", True)
            return added_items

    def remove(self, item):
        """Remove item from container"""
        if item.itemid in self.items:
            self.items.remove(item)

    def count(self, state) -> int:
        """Count items with given state in container"""
        return len(self.get_items_with_state(state))

    def get_items_with_state(self, state):
        """Get items that need to be updated"""
        return MediaItemContainer([item for item in self.items.values() if item.state == state])

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
