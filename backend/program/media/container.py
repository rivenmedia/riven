import os
import shutil
import tempfile
import threading
from typing import Dict, Generator, Optional

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
    def __init__(self):
        self._items = {}
        self._shows = {}
        self._seasons = {}
        self._episodes = {}
        self._movies = {}
        self._imdb_index = {}
        self.lock = ReadWriteLock()

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

    def get_imdbid(self, imdb_id: str) -> Optional[MediaItem]:
        self.lock.acquire_read()
        try:
            return self._imdb_index.get(imdb_id)
        finally:
            self.lock.release_read()

    def get_item_by_id(self, item_id: ItemId) -> Optional[MediaItem]:
        """Retrieve an item by its ID from the container."""
        self.lock.acquire_read()
        try:
            return self._items.get(item_id)
        finally:
            self.lock.release_read()

    def upsert(self, item: MediaItem) -> None:
        self.lock.acquire_write()
        try:
            if item.item_id in self._items:
                existing_item = self._items[item.item_id]
                if existing_item.state == States.Completed and existing_item.title:
                    return
                self._merge_items(existing_item, item)
            else:
                self._items[item.item_id] = item
                self._index_item(item)
        finally:
            self.lock.release_write()

    def _merge_items(self, existing_item, new_item):
        """Merge new item data into existing item without losing existing state."""
        if existing_item.state == States.Completed and new_item.state != States.Completed:
            return
        for attr in vars(new_item):
            new_value = getattr(new_item, attr)
            if new_value is not None:
                setattr(existing_item, attr, new_value)
        if isinstance(existing_item, Show):
            for season in new_item.seasons:
                if season.item_id in self._seasons:
                    self._merge_items(self._seasons[season.item_id], season)
                else:
                    self._index_item(season)
        elif isinstance(existing_item, Season):
            for episode in new_item.episodes:
                if episode.item_id in self._episodes:
                    self._merge_items(self._episodes[episode.item_id], episode)
                else:
                    if not self._episode_exists(existing_item, episode):
                        self._index_item(episode)

    def _episode_exists(self, season, episode):
        for existing_episode in season.episodes:
            if existing_episode.item_id == episode.item_id:
                return True
        return False

    def _index_item(self, item: MediaItem):
        """Index the item and its children in the appropriate dictionaries."""
        if item.imdb_id:
            self._imdb_index[item.imdb_id] = item
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
        elif isinstance(item, Season):
            self._seasons[item.item_id] = item
            for episode in item.episodes:
                episode.parent = item
                self._items[episode.item_id] = episode
                self._episodes[episode.item_id] = episode
            if item.item_id.parent_id in self._shows:
                show = self._shows[item.item_id.parent_id]
                show.seasons.append(item)
        elif isinstance(item, Episode):
            self._episodes[item.item_id] = item
            if item.item_id.parent_id in self._seasons:
                season = self._seasons[item.item_id.parent_id]
                season.episodes.append(item)
        elif isinstance(item, Movie):
            self._movies[item.item_id] = item

    def remove(self, item) -> None:
        self.lock.acquire_write()
        try:
            if item.item_id in self._items:
                del self._items[item.item_id]
                if item.imdb_id in self._imdb_index:
                    del self._imdb_index[item.imdb_id]
                if isinstance(item, Show):
                    del self._shows[item.item_id]
                    for season in item.seasons:
                        del self._items[season.item_id]
                        del self._seasons[season.item_id]
                        for episode in season.episodes:
                            del self._items[episode.item_id]
                            del self._episodes[episode.item_id]
                elif isinstance(item, Season):
                    del self._seasons[item.item_id]
                    for episode in item.episodes:
                        del self._items[episode.item_id]
                        del self._episodes[episode.item_id]
                elif isinstance(item, Episode):
                    del self._episodes[item.item_id]
                elif isinstance(item, Movie):
                    del self._movies[item.item_id]
        finally:
            self.lock.release_write()

    def get_incomplete_items(self) -> Dict[ItemId, MediaItem]:
        """Get all items that are not in a completed state."""
        self.lock.acquire_read()
        try:
            media_items = self._items
            return {
                item_id: item
                for item_id, item in media_items.items()
                if item.state is not States.Completed
            }
        finally:
            self.lock.release_read()

    def save(self, filename):
        if not self._items:
            return

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
            # logger.success("Successfully saved %d items.", len(self._items))
        except Exception as e:
            logger.error(f"Failed to replace old file with new file: {e}")
            try:
                os.remove(temp_file.name)
            except OSError as remove_error:
                logger.error(f"Failed to remove temporary file: {remove_error}")

    def load(self, filename):
        try:
            with open(filename, "rb") as file:
                from_disk: MediaItemContainer = dill.load(file)  # noqa: S301
        except FileNotFoundError:
            logger.error(f"Cannot find cached media data at {filename}")
            return
        except (EOFError, dill.UnpicklingError) as e:
            logger.error(f"Failed to unpickle media data: {e}. Starting fresh.")
            return
        if not isinstance(from_disk, MediaItemContainer):
            logger.error("Loaded data is malformed. Resetting to blank slate.")
            return

        with self.lock:
            self._items = from_disk._items
            self._shows = from_disk._shows
            self._seasons = from_disk._seasons
            self._episodes = from_disk._episodes
            self._movies = from_disk._movies
            self._imdb_index = from_disk._imdb_index

        logger.success(f"Loaded {len(self._items)} items from {filename}")
