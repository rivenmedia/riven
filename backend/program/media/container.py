import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Dict, Generator, List, Optional

import dill
from program.media.item import Episode, ItemId, MediaItem, Movie, Season, Show
from program.media.state import States
from utils.logger import logger


class ReadWriteLock:
    def __init__(self):
        self._read_ready = threading.Condition(threading.Lock())
        self._readers = 0

    def acquire_read(self):
        with self._read_ready:
            self._readers += 1

    def release_read(self):
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    def acquire_write(self):
        self._read_ready.acquire()
        while self._readers > 0:
            self._read_ready.wait()

    def release_write(self):
        self._read_ready.release()

    def __enter__(self):
        self.acquire_write()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release_write()


class MediaItemContainer:
    """A container to store media items."""

    def __init__(self):
        self._items: Dict[ItemId, MediaItem] = {}
        self.library_file: str = "media.pkl"
        self.lock: ReadWriteLock = ReadWriteLock()

    @property
    def movies(self) -> Dict[ItemId, Movie]:
        """Retrieve all movies in the container."""
        return {item_id: item for item_id, item in self._items.items() if isinstance(item, Movie)}

    @property
    def shows(self) -> Dict[ItemId, Show]:
        """Retrieve all shows in the container."""
        return {item_id: item for item_id, item in self._items.items() if isinstance(item, Show)}

    @property
    def seasons(self) -> Dict[ItemId, Season]:
        """Retrieve all seasons in the container."""
        return {item_id: item for item_id, item in self._items.items() if isinstance(item, Season)}

    @property
    def episodes(self) -> Dict[ItemId, Episode]:
        """Retrieve all episodes in the container."""
        return {item_id: item for item_id, item in self._items.items() if isinstance(item, Episode)}

    @property
    def incomplete_episodes(self) -> List[Episode]:
        """Retrieve all episodes that are in an incomplete or partially completed state."""
        incomplete_episodes = [
            item for item in self.episodes.values() 
            if item.state not in (States.Completed, States.PartiallyCompleted)
        ]
        logger.debug(f"Found {len(incomplete_episodes)} incomplete episodes.")
        return incomplete_episodes

    def __iter__(self) -> Generator[MediaItem, None, None]:
        self.lock.acquire_read()
        try:
            for item in self._items.values():
                yield item
        finally:
            self.lock.release_read()

    def __contains__(self, item) -> bool:
        self.lock.acquire_read()
        try:
            return item in self._items
        finally:
            self.lock.release_read()

    def __len__(self) -> int:
        self.lock.acquire_read()
        try:
            return len(self._items)
        finally:
            self.lock.release_read()

    def __getitem__(self, item_id: ItemId) -> MediaItem:
        self.lock.acquire_read()
        try:
            return self._items[item_id]
        finally:
            self.lock.release_read()

    def get(self, key, default=None) -> MediaItem:
        self.lock.acquire_read()
        try:
            return self._items.get(key, default)
        finally:
            self.lock.release_read()

    def get_episodes(self, show_id: ItemId) -> List[MediaItem]:
        """Get all episodes for a show."""
        self.lock.acquire_read()
        try:
            return self.shows[show_id].episodes
        finally:
            self.lock.release_read()

    def upsert(self, item: MediaItem) -> None:
        """Upsert an item into the container."""
        self.lock.acquire_write()
        try:
            if item.item_id in self._items:
                existing_item = self._items[item.item_id]
                self._merge_items(existing_item, item)
            else:
                self._index_item(item)
        finally:
            self.lock.release_write()

    def _merge_items(self, existing_item: MediaItem, new_item: MediaItem) -> None:
        """Merge new item data into existing item without losing existing state."""
        if existing_item.state == States.Completed and new_item.state != States.Completed:
            return
        for attr in vars(new_item):
            new_value = getattr(new_item, attr)
            if new_value is not None and getattr(existing_item, attr) != new_value:
                setattr(existing_item, attr, new_value)
        if isinstance(existing_item, Show):
            for season in new_item.seasons:
                existing_season = next((s for s in existing_item.seasons if s.item_id == season.item_id), None)
                if existing_season:
                    self._merge_items(existing_season, season)
                else:
                    existing_item.seasons.append(season)
                    season.parent = existing_item

    def _index_item(self, item: MediaItem):
        """Index the item and its children in the appropriate dictionaries."""
        self._items[item.item_id] = item
        if isinstance(item, Show):
            for season in item.seasons:
                season.parent = item
                season.item_id.parent_id = item.item_id
                self._index_item(season)
        elif isinstance(item, Season):
            for episode in item.episodes:
                episode.parent = item
                episode.item_id.parent_id = item.item_id
                self._index_item(episode)

    def remove(self, item: MediaItem) -> None:
        """Remove an item, which could be a movie, show, season, or episode."""
        if item is None:
            logger.error("Attempted to remove a None item.")
            return

        log_title = item.log_string
        imdb_id = item.imdb_id

        self.lock.acquire_write()
        try:
            if isinstance(item, Episode):
                parent_season = item.parent
                if parent_season:
                    parent_season.episodes.remove(item)
                self._remove_item(item)
            elif isinstance(item, Season):
                parent_show = item.parent
                if parent_show:
                    parent_show.seasons.remove(item)
                for episode in item.episodes:
                    self._remove_item(episode)
                self._remove_item(item)
            elif isinstance(item, Show):
                for season in item.seasons:
                    for episode in season.episodes:
                        self._remove_item(episode)
                    self._remove_item(season)
                self._remove_item(item)
            elif isinstance(item, Movie):
                self._remove_item(item)
            logger.debug(f"Removed item: {log_title} (IMDb ID: {imdb_id})")
            self.save("media.pkl")
        except KeyError as e:
            logger.error(f"Failed to remove item: {log_title} (IMDb ID: {imdb_id}). KeyError: {e}")
        finally:
            self.lock.release_write()

    def _remove_item(self, item: MediaItem) -> None:
        """Helper method to remove an item from the container."""
        item_id: ItemId = item.item_id
        if item_id in self._items:
            del self._items[item_id]
            logger.debug(f"Successfully removed item with ID: {item_id}")
        else:
            logger.error(f"Item ID {item_id} not found in _items.")

    def get_incomplete_episodes(self) -> List[Episode]:
        """Retrieve all episodes that are in an incomplete state."""
        incomplete_episodes = []
        for item in self._items.values():
            if isinstance(item, Episode) and item.state != States.Completed:
                incomplete_episodes.append(item)
        return incomplete_episodes

    def save(self, filename: str = "media.pkl") -> None:
        """Save the container to a file."""
        with self.lock, tempfile.NamedTemporaryFile(delete=False, mode="wb") as temp_file:
            try:
                dill.dump(self, temp_file, dill.HIGHEST_PROTOCOL)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            except Exception as e:
                logger.error(f"Failed to serialize data: {e}")
                return

            try:
                backup_filename = filename + ".bak"
                if os.path.exists(filename):
                    shutil.copyfile(filename, backup_filename)
                shutil.move(temp_file.name, filename)
            except Exception as e:
                logger.error(f"Failed to replace old file with new file: {e}")
                try:
                    os.remove(temp_file.name)
                except OSError as remove_error:
                    logger.error(f"Failed to remove temporary file: {remove_error}")

    def load(self, filename: str = "media.pkl") -> None:
        """Load the container from a file."""
        from_disk: Optional[MediaItemContainer] = None
        try:
            with open(filename, "rb") as file:
                from_disk = dill.load(file)
                if not isinstance(from_disk, MediaItemContainer):
                    logger.debug("Loaded data is malformed. Resetting to blank slate.")
                    return
        except FileNotFoundError:
            logger.debug("No media data found. Starting fresh.")
        except Exception as e:
            logger.debug(f"Failed to load media data: {e}. Starting fresh.")
            return

        if from_disk is None:
            return

        with self.lock:
            self._items = from_disk._items
            # Reconstruct parent-child relationships
            for item in self._items.values():
                if isinstance(item, (Season, Episode)):
                    parent = self._items.get(item.item_id.parent_id)
                    if parent:
                        item.parent = parent
                        if isinstance(item, Season):
                            parent.seasons.append(item)
                        elif isinstance(item, Episode):
                            parent.episodes.append(item)

        logger.success(f"Loaded {len(self._items)} items from {filename}")