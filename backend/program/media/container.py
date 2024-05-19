import hashlib
import os
import shutil
import tempfile
import threading
from typing import Dict, Generator

import dill
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
        self.lock = ReadWriteLock()

    def __iter__(self) -> Generator:
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

    def __getitem__(self, item_id) -> object:
        self.lock.acquire_read()
        try:
            return self._items[item_id]
        finally:
            self.lock.release_read()

    def get(self, key, default=None) -> object:
        self.lock.acquire_read()
        try:
            return self._items.get(key, default)
        finally:
            self.lock.release_read()

    def upsert(self, item) -> None:
        self.lock.acquire_write()
        try:
            if item.item_id in self._items:
                # logger.debug(f"Updating existing item: {item}")
                existing_item = self._items[item.item_id]
                self._merge_items(existing_item, item)
            else:
                # logger.debug(f"Inserting new item: {item}")
                self._items[item.item_id] = item
        finally:
            self.lock.release_write()

    def _merge_items(self, existing_item, new_item):
        """Merge new item data into existing item without losing existing state."""
        # Update the existing item with new attributes from new_item
        for attr in vars(new_item):
            if getattr(new_item, attr) is not None:
                setattr(existing_item, attr, getattr(new_item, attr))

        # Merge streams specifically to avoid overwriting
        existing_item.streams.update(new_item.streams)
        existing_item.scraped_times = max(existing_item.scraped_times, new_item.scraped_times)
        existing_item.symlinked_times = max(existing_item.symlinked_times, new_item.symlinked_times)

    def remove(self, item) -> None:
        self.lock.acquire_write()
        try:
            if item.item_id in self._items:
                del self._items[item.item_id]
        finally:
            self.lock.release_write()

    def get_incomplete_items(self) -> Dict:
        """Get items that are not in the COMPLETED state."""
        self.lock.acquire_read()
        try:
            return {item_id: item for item_id, item in self._items.items() if item.state != "COMPLETED"}
        finally:
            self.lock.release_read()

    def save(self, filename):
        """Save media data to file with better error handling and using context managers."""
        if not self._items:
            return

        with self.lock, tempfile.NamedTemporaryFile(delete=False, mode="wb") as temp_file:
            try:
                # Serialize the data to a temporary file first to avoid corruption of the main file on error
                dill.dump(self, temp_file, dill.HIGHEST_PROTOCOL)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            except Exception as e:
                logger.error("Failed to serialize data: %s", e)
                return

        try:
            backup_filename = filename + ".bak"
            if os.path.exists(filename):
                shutil.copyfile(filename, backup_filename)
            shutil.move(temp_file.name, filename)

            # This gets a bit spammy with it logging every minute.. use only for debugging if needed.
            logger.debug("Successfully saved %d items.", len(self._items))
        except Exception as e:
            logger.error("Failed to replace old file with new file: %s", e)
            try:
                os.remove(temp_file.name)
            except OSError as remove_error:
                logger.error("Failed to remove temporary file: %s", remove_error)

    def load(self, filename):
        """Load media data from a file with improved error handling and integrity checks."""
        try:
            with open(filename, "rb") as file:
                from_disk: MediaItemContainer = dill.load(file)  # noqa: S301
        except FileNotFoundError:
            logger.error("Cannot find cached media data at %s", filename)
            return
        except (EOFError, dill.UnpicklingError) as e:
            logger.error("Failed to unpickle media data: %s. Starting fresh.", e)
            return
        if not isinstance(from_disk, MediaItemContainer):
            logger.error("Loaded data is malformed. Resetting to blank slate.")
            return

        with self.lock:
            # Ensure thread safety while updating the container's internal state
            self._items = from_disk._items

        logger.info("Loaded %s items from %s", len(self._items), filename)


class ShardedMediaItemContainer:
    def __init__(self, num_shards=4):
        self.shards = [MediaItemContainer() for _ in range(num_shards)]

    def _get_shard(self, item_id) -> MediaItemContainer:
        shard_index = int(hashlib.sha256(str(item_id).encode()).hexdigest(), 16) % len(self.shards)
        return self.shards[shard_index]

    def __iter__(self) -> Generator:
        for shard in self.shards:
            for item in shard:
                yield item

    def __contains__(self, item) -> bool:
        return item in self._get_shard(item.item_id)

    def __len__(self) -> int:
        return sum(len(shard) for shard in self.shards)

    def __getitem__(self, item_id) -> object:
        return self._get_shard(item_id)[item_id]

    def get(self, key, default=None) -> object:
        return self._get_shard(key).get(key, default)

    def upsert(self, item) -> None:
        self._get_shard(item.item_id).upsert(item)

    def remove(self, item) -> None:
        self._get_shard(item.item_id).remove(item)

    def get_incomplete_items(self) -> Dict:
        """Get items that are not in the COMPLETED state from all shards."""
        incomplete_items = {}
        for shard in self.shards:
            incomplete_items.update(shard.get_incomplete_items())
        return incomplete_items

    def save(self, filename):
        """Save all shards to separate files."""
        for i, shard in enumerate(self.shards):
            shard_filename = f"{filename}.shard{i}"
            shard.save(shard_filename)

    def load(self, filename):
        """Load all shards from separate files."""
        for i, shard in enumerate(self.shards):
            shard_filename = f"{filename}.shard{i}"
            shard.load(shard_filename)
