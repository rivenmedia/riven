import os
import shutil
import tempfile
import threading
from copy import copy
from pickle import UnpicklingError
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
        self._shows: Dict[ItemId, Show] = {}
        self._seasons: Dict[ItemId, Season] = {}
        self._episodes: Dict[ItemId, Episode] = {}
        self._movies: Dict[ItemId, Movie] = {}
        self.library_file: str = "media.pkl"
        self.lock: ReadWriteLock = ReadWriteLock()

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

    @property
    def seasons(self) -> dict[ItemId, Season]:
        return copy(self._seasons)

    @property
    def episodes(self) -> dict[ItemId, Episode]:
        return copy(self._episodes)

    @property
    def shows(self) -> dict[ItemId, Show]:
        return copy(self._shows)

    @property
    def movies(self) -> dict[ItemId, Movie]:
        return copy(self._movies)

    def get_items_with_state(self, state) -> dict[ItemId, MediaItem]:
        """Get items with the specified state"""
        return {
            item_id: self[item_id]
            for item_id, item in self._items.items()
            if item.state == state
        }

    def get_incomplete_items(self) -> dict[ItemId, MediaItem]:
        """Get items that are not completed."""
        self.lock.acquire_read()
        try:
            incomplete_items = {}
            items_copy = list(self._items.items())  # Create a copy of the dictionary items
            for item_id, item in items_copy:
                if isinstance(item, Show):
                    if item.state not in [States.Completed]:
                        incomplete_items[item_id] = item
                elif isinstance(item, Movie):
                    if item.state not in [States.Completed, States.PartiallyCompleted]:
                        incomplete_items[item_id] = item
            return incomplete_items
        finally:
            self.lock.release_read()

    def get_item(self, identifier: str | ItemId) -> Optional[MediaItem]:
        """Retrieve an item by its IMDb ID or item ID from the container."""
        self.lock.acquire_read()
        try:
            if isinstance(identifier, str) and identifier.startswith("tt"):
                return self._items.get(ItemId(identifier))
            if isinstance(identifier, ItemId):
                return self._items.get(identifier)
            return None
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
        """Iterate through the input item and upsert all parents and children."""
        if not item:
            logger.error(f"Item is None: {item}")
            return

        self._items[item.item_id] = item
        detatched = item.item_id.parent_id is None or item.parent is None
        if isinstance(item, (Season, Episode)) and detatched:
            if not item or not getattr(item, 'log_string', None):
                logger.error(f"Detached item cannot be upserted into the database")
            else:
                logger.error(
                    f"{item.__class__.__name__} item {item.log_string} is detatched " +
                    "and not associated with a parent, and thus" +
                    " it cannot be upserted into the database"
                )
            del self._items[item.item_id]
            return
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

    def remove(self, items):
        """Remove a list of items, which could be movies, shows, seasons, or episodes."""
        self.lock.acquire_write()
        try:
            for item in items:
                self._remove_item(item)
            logger.debug(f"Removed items: {[item.log_string for item in items]}")
        except Exception as e:
            logger.error(f"Unexpected error occurred while removing items: {e}")
        finally:
            self.lock.release_write()

    def _remove_item(self, item):
        """Helper method to remove an item from the container."""
        item_id = item.item_id
        if item_id in self._items:
            del self._items[item_id]
            logger.debug(f"Successfully removed item with ID: {item_id}")
        else:
            logger.error(f"Item ID {item_id} not found in _items.")

    def count(self, state) -> int:
        """Count items with given state in container"""
        return len(self.get_items_with_state(state))

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
        try:
            with open(filename, "rb") as file:
                from_disk = dill.load(file)
                self._items = from_disk._items
                self._movies = from_disk._movies
                self._shows = from_disk._shows
                self._seasons = from_disk._seasons
                self._episodes = from_disk._episodes
        except FileNotFoundError:
            pass
        except (EOFError, UnpicklingError):
            logger.error(f"Failed to unpickle media data at {filename}, wiping cached data")
            os.remove(filename)
            self._items = {}
            self._movies = {}
            self._shows = {}
            self._seasons = {}
            self._episodes = {}

    def log(self):
        """Log the items in the container."""
        movies_symlinks = self._count_symlinks(self._movies)
        episodes_symlinks = self._count_symlinks(self._episodes)
        total_symlinks = movies_symlinks + episodes_symlinks

        logger.log("ITEM", f"Movies: {len(self._movies)} (Symlinks: {movies_symlinks})")
        logger.log("ITEM", f"Shows: {len(self._shows)}")
        logger.log("ITEM", f"Seasons: {len(self._seasons)}")
        logger.log("ITEM", f"Episodes: {len(self._episodes)} (Symlinks: {episodes_symlinks})")
        logger.log("ITEM", f"Total Items: {len(self._items)} (Symlinks: {total_symlinks})")

    def _count_symlinks(self, items):
        """Count the number of symlinks in the given items."""
        return sum(1 for item in items.values() if item.symlinked)