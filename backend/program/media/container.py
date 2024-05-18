import os
import shutil
import tempfile
import threading
from typing import Dict, Generator

import dill
from program.media.item import Episode, ItemId, MediaItem, Movie, Season, Show
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
        self.lock = threading.Lock()

    def __iter__(self) -> Generator[MediaItem, None, None]:
        for item in self._items.values():
            yield item

    def __contains__(self, item) -> bool:
        return item in self._items

    def __len__(self) -> int:
        """Get length of container"""
        return len(self._items)

    def __getitem__(self, item_id: ItemId) -> MediaItem:
        return self._items[item_id]

    def get(self, key, default=None) -> MediaItem:
        return self._items.get(key, default)

    @property
    def seasons(self) -> dict[ItemId, Season]:
        with self.lock:
            return self._seasons

    @property
    def episodes(self) -> dict[ItemId, Episode]:
        with self.lock:
            return self._episodes

    @property
    def shows(self) -> dict[ItemId, Show]:
        with self.lock:
            return self._shows

    @property
    def movies(self) -> dict[ItemId, Movie]:
        with self.lock:
            return self._movies

    def upsert(self, item: MediaItem) -> None:  # noqa: C901
        """Iterate through the input item and upsert all parents and children."""
        # Use deepcopy so that further modifications made to the input item
        # will not affect the container state
        # item = deepcopy(item)
        self._items[item.item_id] = item
        detatched = item.item_id.parent_id is None or item.parent is None
        if isinstance(item, (Season, Episode)) and detatched:
            logger.error(
                "%s item %s is detatched and not associated with a parent, and thus"
                + " it cannot be upserted into the database",
                item.__class__.name,
                item.log_string,
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

    def remove(self, item: MediaItem) -> None:
        """Remove an item from the container."""
        with self.lock:
            if item.id in self._items:
                del self._items[item.id]
                if isinstance(item, Show):
                    del self._shows[item.id]
                    for season in item.seasons:
                        del self._seasons[season.id]
                        for episode in season.episodes:
                            del self._episodes[episode.id]
                    logger.info("Removed %s and all its children", item.log_string)
                elif isinstance(item, Season):
                    del self._seasons[item.id]
                    for episode in item.episodes:
                        del self._episodes[episode.id]
                    logger.info("Removed %s and all its children", item.log_string)
                elif isinstance(item, Episode):
                    del self._episodes[item.id]
                    logger.info("Removed %s", item.log_string)
                elif isinstance(item, Movie):
                    del self._movies[item.id]
                    logger.info("Removed %s", item.log_string)

    def count(self, state: str) -> int:
        """Count items with given state in the container."""
        return len(self.get_items_with_state(state))

    def get_items_with_state(self, state: str) -> Dict[ItemId, MediaItem]:
        """Get items with the specified state."""
        return {item_id: item for item_id, item in self._items.items() if item.state == state}


    def get_incomplete_items(self) -> dict[ItemId, MediaItem]:
        """Get items with the specified state."""
        return {
                # direct self access deep copies the item before passing it
                item_id: self[item_id]
                # We need to copy first in case there are additions or deletions while we are iterating
                for item_id, item in self._items.items()
                if item.state not in (States.Completed, States.PartiallyCompleted)
        }

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
            # logger.debug("Successfully saved %d items to %s", len(self._items), filename)
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
                from_disk: MediaItemContainer = dill.load(file) # noqa: S301
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
            self._movies = from_disk._movies
            self._shows = from_disk._shows
            self._seasons = from_disk._seasons
            self._episodes = from_disk._episodes

        logger.info("Loaded %s items from %s", len(self._items), filename)
