import os
import random
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Union, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from loguru import logger
from sqlalchemy import select

from program.db.db import db
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.settings.manager import settings_manager


class Symlinker:
    """
    A class that represents a symlinker thread.

    Settings Attributes:
        rclone_path (str): The absolute path of the rclone mount root directory.
        library_path (str): The absolute path of the location we will create our symlinks that point to the rclone_path.
    """

    def __init__(self):
        self.key = "symlink"
        self.settings = settings_manager.settings.symlink
        self.rclone_path = self.settings.rclone_path

        # Performance optimization caches
        self._path_cache = {}  # Cache for path validations
        self._folder_cache = set()  # Cache for created folders
        self._cache_lock = threading.RLock()

        # Batch processing settings
        self._batch_size = 10  # Process symlinks in batches
        self._max_workers = min(4, os.cpu_count() or 1)  # Limit concurrent operations

        self.initialized = self.validate()
        if not self.initialized:
            return
        logger.info(f"Rclone path symlinks are pointed to: {self.rclone_path}")
        logger.info(f"Symlinks will be placed in: {self.settings.library_path}")
        logger.success("Symlink initialized!")

    def validate(self):
        """Validate paths and create the initial folders."""
        library_path = self.settings.library_path
        if not self.rclone_path or not library_path:
            logger.error("rclone_path or library_path not provided.")
            return False
        if self.rclone_path == Path(".") or library_path == Path("."):
            logger.error("rclone_path or library_path is set to the current directory.")
            return False
        if not self.rclone_path.exists():
            logger.error(f"rclone_path does not exist: {self.rclone_path}")
            return False
        if not library_path.exists():
            logger.error(f"library_path does not exist: {library_path}")
            return False
        if not self.rclone_path.is_absolute():
            logger.error(f"rclone_path is not an absolute path: {self.rclone_path}")
            return False
        if not library_path.is_absolute():
            logger.error(f"library_path is not an absolute path: {library_path}")
            return False
        return self._create_initial_folders()

    def _create_initial_folders(self):
        """Create the initial library folders."""
        try:
            self.library_path_movies = self.settings.library_path / "movies"
            self.library_path_shows = self.settings.library_path / "shows"
            self.library_path_anime_movies = self.settings.library_path / "anime_movies"
            self.library_path_anime_shows = self.settings.library_path / "anime_shows"
            folders = [
                self.library_path_movies,
                self.library_path_shows,
                self.library_path_anime_movies,
                self.library_path_anime_shows,
            ]
            for folder in folders:
                if not folder.exists():
                    folder.mkdir(parents=True, exist_ok=True)
        except FileNotFoundError as e:
            logger.error(f"Path not found when creating directory: {e}")
            return False
        except PermissionError as e:
            logger.error(f"Permission denied when creating directory: {e}")
            return False
        except OSError as e:
            logger.error(f"OS error when creating directory: {e}")
            return False
        return True

    def run(self, item: Union[Movie, Show, Season, Episode]):
        """Check if the media item exists and create a symlink if it does"""
        items = self._get_items_to_update(item)
        if not items:
            logger.debug(f"No items to symlink for {item.log_string}")
            yield item

        if not self._should_submit(items):
            if item.symlinked_times == 6:
                logger.log("SYMLINKER", f"Soft resetting {item.log_string} because required files were not found")
                for _item in items:
                    _item.soft_reset()
                if item.type in ("show", "season"):
                    item.soft_reset()
                yield item
            next_attempt = self._calculate_next_attempt(item)
            logger.log("SYMLINKER", f"Waiting for {item.log_string} to become available, next attempt in {round((next_attempt - datetime.now()).total_seconds())} seconds")
            item.symlinked_times += 1
            yield (item, next_attempt)

        try:
            for _item in items:
                symlinked = False
                if self._symlink(_item):
                    symlinked = True
                if symlinked:
                    logger.log("SYMLINKER", f"Symlinks created for {_item.log_string}")
                if not symlinked:
                    logger.log("SYMLINKER", f"No symlinks created for {_item.log_string}")
                    _item.soft_reset()
                    logger.debug(f"Item {_item.log_string} has been soft reset")
        except Exception as e:
            logger.error(f"Exception thrown when creating symlink for {item.log_string}: {e}")

        yield item

    def _calculate_next_attempt(self, item: Union[Movie, Show, Season, Episode]) -> datetime:
        base_delay = timedelta(seconds=4)
        next_attempt_delay = base_delay * (2 ** item.symlinked_times)
        next_attempt_time = datetime.now() + next_attempt_delay
        return next_attempt_time

    def _should_submit(self, items: Union[Movie, Show, Season, Episode]) -> bool:
        """Check if the item should be submitted for symlink creation."""
        random_item = random.choice(items)
        if not _get_item_path(random_item):
            return False
        else:
            return True

    def _get_items_to_update(self, item: Union[Movie, Show, Season, Episode]) -> List[Union[Movie, Episode]]:
        if item.type in ["movie", "episode"]:
            return [item]
        elif item.type == "show":
            return [episode for season in item.seasons for episode in season.episodes if episode.state == States.Downloaded]
        elif item.type == "season":
            return [episode for episode in item.episodes if episode.state == States.Downloaded]
        return []

    def symlink(self, item: Union[Movie, Episode]) -> bool:
        """Create a symlink for the given media item if it does not already exist."""
        return self._symlink(item)

    def symlink_batch(self, items: List[Union[Movie, Episode]]) -> List[bool]:
        """
        Create symlinks for multiple items in batches for better performance.

        Args:
            items: List of media items to create symlinks for

        Returns:
            List of boolean results indicating success/failure for each item
        """
        if not items:
            return []

        results = [False] * len(items)

        # Process items in batches to reduce filesystem overhead
        for i in range(0, len(items), self._batch_size):
            batch = items[i:i + self._batch_size]
            batch_results = self._process_symlink_batch(batch)

            # Update results
            for j, result in enumerate(batch_results):
                results[i + j] = result

        return results

    def _process_symlink_batch(self, batch: List[Union[Movie, Episode]]) -> List[bool]:
        """Process a batch of symlink operations with concurrent execution."""
        if not batch:
            return []

        # Pre-validate and prepare all items
        prepared_items = []
        for item in batch:
            prepared = self._prepare_symlink_item(item)
            if prepared:
                prepared_items.append(prepared)

        if not prepared_items:
            return [False] * len(batch)

        # Execute symlink operations concurrently
        results = [False] * len(batch)

        with ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="symlink-batch") as executor:
            # Submit all symlink operations
            future_to_index = {}
            for i, (item, source, destination) in enumerate(prepared_items):
                future = executor.submit(self._create_symlink_atomic, item, source, destination)
                future_to_index[future] = i

            # Collect results
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    logger.error(f"Error in batch symlink operation: {e}")
                    results[index] = False

        return results

    def _prepare_symlink_item(self, item: Union[Movie, Episode]) -> Optional[Tuple[Union[Movie, Episode], str, str]]:
        """
        Prepare an item for symlink creation by validating paths and determining destination.

        Returns:
            Tuple of (item, source_path, destination_path) or None if preparation failed
        """
        if not item:
            logger.error(f"Invalid item sent to Symlinker: {item}")
            return None

        source = self._get_item_path_cached(item)
        if not source:
            logger.error(f"Could not find path for {item.log_string} in rclone path, cannot create symlink.")
            return None

        filename = self._determine_file_name(item)
        if not filename:
            logger.error(f"Symlink filename is None for {item.log_string}, cannot create symlink.")
            return None

        extension = os.path.splitext(item.file)[1][1:]
        symlink_filename = f"{filename}.{extension}"
        destination = self._create_item_folders_cached(item, symlink_filename)

        return (item, source, destination)

    def _create_symlink_atomic(self, item: Union[Movie, Episode], source: str, destination: str) -> bool:
        """
        Atomically create a symlink with optimized error handling.

        Args:
            item: Media item
            source: Source path
            destination: Destination path

        Returns:
            True if symlink was created successfully
        """
        try:
            # Remove existing symlink if present
            if os.path.islink(destination):
                os.remove(destination)

            # Create the symlink
            os.symlink(source, destination)

            # Quick validation (avoid Path.readlink() for better performance)
            if not os.path.islink(destination):
                logger.error(f"Symlink creation failed for {item.log_string}: {destination}")
                return False

            # Update item attributes
            item.set("symlinked", True)
            item.set("symlinked_at", datetime.now())
            item.set("symlinked_times", item.symlinked_times + 1)
            item.set("symlink_path", destination)

            return True

        except PermissionError as e:
            logger.exception(f"Permission denied when creating symlink for {item.log_string}: {e}")
            return False
        except OSError as e:
            if e.errno == 36:
                logger.error(f"Filename too long when creating symlink for {item.log_string}: {e}")
            else:
                logger.error(f"OS error when creating symlink for {item.log_string}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error creating symlink for {item.log_string}: {e}")
            return False

    def _symlink(self, item: Union[Movie, Episode]) -> bool:
        """Create a symlink for the given media item if it does not already exist."""
        if not item:
            logger.error(f"Invalid item sent to Symlinker: {item}")
            return False

        source = _get_item_path(item)
        if not source:
            logger.error(f"Could not find path for {item.log_string} in rclone path, cannot create symlink.")
            return False

        filename = self._determine_file_name(item)
        if not filename:
            logger.error(f"Symlink filename is None for {item.log_string}, cannot create symlink.")
            return False

        extension = os.path.splitext(item.file)[1][1:]
        symlink_filename = f"{filename}.{extension}"
        destination = self._create_item_folders(item, symlink_filename)

        try:
            if os.path.islink(destination):
                os.remove(destination)
            os.symlink(source, destination)
        except PermissionError as e:
            # This still creates the symlinks, however they will have wrong perms. User needs to fix their permissions.
            # TODO: Maybe we validate symlink class by symlinking a test file, then try removing it and see if it still exists
            logger.exception(f"Permission denied when creating symlink for {item.log_string}: {e}")
        except OSError as e:
            if e.errno == 36:
                # This will cause a loop if it hits this.. users will need to fix their paths
                # TODO: Maybe create an alternative naming scheme to cover this?
                logger.error(f"Filename too long when creating symlink for {item.log_string}: {e}")
            else:
                logger.error(f"OS error when creating symlink for {item.log_string}: {e}")
            return False

        if Path(destination).readlink() != source:
            logger.error(f"Symlink validation failed: {destination} does not point to {source} for {item.log_string}")
            return False

        item.set("symlinked", True)
        item.set("symlinked_at", datetime.now())
        item.set("symlinked_times", item.symlinked_times + 1)
        item.set("symlink_path", destination)
        return True

    def _create_item_folders(self, item: Union[Movie, Show, Season, Episode], filename: str) -> str:
        """Create necessary folders and determine the destination path for symlinks."""
        is_anime: bool = hasattr(item, "is_anime") and item.is_anime

        movie_path: Path = self.library_path_movies
        show_path: Path = self.library_path_shows

        if self.settings.separate_anime_dirs and is_anime:
            if isinstance(item, Movie):
                movie_path = self.library_path_anime_movies
            elif isinstance(item, (Show, Season, Episode)):
                show_path = self.library_path_anime_shows

        def create_folder_path(base_path, *subfolders):
            path = os.path.join(base_path, *subfolders)
            os.makedirs(path, exist_ok=True)
            return path

        if isinstance(item, Movie):
            movie_folder = f"{item.title.replace('/', '-')} ({item.aired_at.year}) {{imdb-{item.imdb_id}}}"
            destination_folder = create_folder_path(movie_path, movie_folder)
            item.set("update_folder", destination_folder)
        elif isinstance(item, Show):
            folder_name_show = f"{item.title.replace('/', '-')} ({item.aired_at.year}) {{imdb-{item.imdb_id}}}"
            destination_folder = create_folder_path(show_path, folder_name_show)
            item.set("update_folder", destination_folder)
        elif isinstance(item, Season):
            show = item.parent
            folder_name_show = f"{show.title.replace('/', '-')} ({show.aired_at.year}) {{imdb-{show.imdb_id}}}"
            show_path = create_folder_path(show_path, folder_name_show)
            folder_season_name = f"Season {str(item.number).zfill(2)}"
            destination_folder = create_folder_path(show_path, folder_season_name)
            item.set("update_folder", destination_folder)
        elif isinstance(item, Episode):
            show = item.parent.parent
            folder_name_show = f"{show.title.replace('/', '-')} ({show.aired_at.year}) {{imdb-{show.imdb_id}}}"
            show_path = create_folder_path(show_path, folder_name_show)
            season = item.parent
            folder_season_name = f"Season {str(season.number).zfill(2)}"
            destination_folder = create_folder_path(show_path, folder_season_name)
            item.set("update_folder", destination_folder)

        return os.path.join(destination_folder, filename.replace("/", "-"))

    def _get_item_path_cached(self, item: Union[Movie, Episode]) -> Optional[str]:
        """Get item path with caching to reduce filesystem calls."""
        cache_key = f"path_{item.id}_{item.file}"

        with self._cache_lock:
            if cache_key in self._path_cache:
                return self._path_cache[cache_key]

        # Get path using existing method
        path = _get_item_path(item)

        with self._cache_lock:
            self._path_cache[cache_key] = path

            # Limit cache size to prevent memory issues
            if len(self._path_cache) > 1000:
                # Remove oldest entries (simple FIFO)
                oldest_keys = list(self._path_cache.keys())[:100]
                for key in oldest_keys:
                    del self._path_cache[key]

        return path

    def _create_item_folders_cached(self, item: Union[Movie, Show, Season, Episode], filename: str) -> str:
        """Create necessary folders with caching to reduce filesystem operations."""
        # Generate a cache key for the folder structure
        if isinstance(item, Movie):
            folder_key = f"movie_{item.title}_{item.aired_at.year if item.aired_at else 'unknown'}"
        elif isinstance(item, Episode):
            show = item.parent.parent
            folder_key = f"show_{show.title}_{show.aired_at.year if show.aired_at else 'unknown'}_s{item.parent.number}"
        else:
            folder_key = f"other_{item.id}"

        destination_folder = None

        with self._cache_lock:
            if folder_key in self._folder_cache:
                # Folder structure already exists, just construct the path
                if isinstance(item, Movie):
                    destination_folder = os.path.join(
                        self.settings.library_path,
                        "movies",
                        f"{item.title} ({item.aired_at.year if item.aired_at else 'Unknown'})"
                    )
                elif isinstance(item, Episode):
                    show = item.parent.parent
                    destination_folder = os.path.join(
                        self.settings.library_path,
                        "shows",
                        f"{show.title} ({show.aired_at.year if show.aired_at else 'Unknown'})",
                        f"Season {str(item.parent.number).zfill(2)}"
                    )

        if not destination_folder:
            # Create folders using existing method and cache the result
            destination_folder = self._create_item_folders(item, filename)

            with self._cache_lock:
                self._folder_cache.add(folder_key)

                # Limit cache size
                if len(self._folder_cache) > 500:
                    # Clear some entries
                    self._folder_cache = set(list(self._folder_cache)[100:])

        return os.path.join(destination_folder, filename.replace("/", "-"))

    def _determine_file_name(self, item: Union[Movie, Episode]) -> str | None:
        """Determine the filename of the symlink."""
        filename = None
        if isinstance(item, Movie):
            filename = f"{item.title} ({item.aired_at.year}) " + "{imdb-" + item.imdb_id + "}"
        elif isinstance(item, Season):
            showname = item.parent.title
            showyear = item.parent.aired_at.year
            filename = f"{showname} ({showyear}) - Season {str(item.number).zfill(2)}"
        elif isinstance(item, Episode):
            episodes_from_file = item.get_file_episodes()
            if len(episodes_from_file) > 1:
                # Use item.number as the starting point and calculate the last episode number.
                # Due to the introduction of standard/absolute episode numbering in scraping and downloading processes,
                # it is no longer possible to assume that the episode numbers in the file align with those in the item.
                first_episode_number = item.number
                last_episode_number = first_episode_number + len(episodes_from_file) - 1
                episode_string = f"e{str(first_episode_number).zfill(2)}-e{str(last_episode_number).zfill(2)}"
            else:
                episode_string = f"e{str(item.number).zfill(2)}"
            if episode_string != "":
                showname = item.parent.parent.title
                showyear = item.parent.parent.aired_at.year
                filename = f"{showname} ({showyear}) - s{str(item.parent.number).zfill(2)}{episode_string}"
        return filename

    def delete_item_symlinks(self, item: "MediaItem") -> bool:
        """Delete symlinks and directories based on the item type."""
        if not isinstance(item, (Movie, Show)):
            logger.debug(f"skipping delete symlink for {item.log_string}: Not a movie or show")
            return False
        item_path = None
        if isinstance(item, Show):
            base_path = self.library_path_anime_shows if item.is_anime else self.library_path_shows
            item_path = base_path / f"{item.title.replace('/', '-')} ({item.aired_at.year}) {{imdb-{item.imdb_id}}}"
        elif isinstance(item, Movie):
            base_path = self.library_path_anime_movies if item.is_anime else self.library_path_movies
            item_path = base_path / f"{item.title.replace('/', '-')} ({item.aired_at.year}) {{imdb-{item.imdb_id}}}"
        return _delete_symlink(item, item_path)

    def delete_item_symlinks_by_id(self, item_id: int) -> bool:
        """Delete symlinks and directories based on the item ID."""
        with db.Session() as session:
            item = session.execute(select(MediaItem).where(MediaItem.id == item_id)).unique().scalar_one()
            if not item:
                logger.error(f"No item found with ID {item_id}")
                return False
            return self.delete_item_symlinks(item)

def _delete_symlink(item: Union[Movie, Show], item_path: Path) -> bool:
    try:
        if item_path.exists():
            shutil.rmtree(item_path)
            logger.debug(f"Deleted symlink Directory for {item.log_string}")
            return True
        else:
            logger.debug(f"Symlink Directory for {item.log_string} does not exist, skipping symlink deletion")
            return True
    except FileNotFoundError as e:
        logger.error(f"File not found error when deleting symlink for {item.log_string}: {e}")
    except PermissionError as e:
        logger.error(f"Permission denied when deleting symlink for {item.log_string}: {e}")
    except Exception as e:
        logger.error(f"Failed to delete symlink for {item.log_string}, error: {e}")
    return False

# Global cache for path resolutions to reduce filesystem calls
_path_resolution_cache = {}
_path_cache_lock = threading.RLock()
_path_cache_max_size = 1000

def _get_item_path(item: Union[Movie, Episode]) -> Optional[Path]:
    """Optimized path resolution with caching and reduced filesystem calls."""
    if not item.file:
        return None

    # Create cache key based on item attributes that affect path resolution
    cache_key = f"{item.id}_{item.file}_{item.folder}_{getattr(item, 'alternative_folder', '')}"

    # Check cache first
    with _path_cache_lock:
        if cache_key in _path_resolution_cache:
            cached_path, cache_time = _path_resolution_cache[cache_key]
            # Cache valid for 5 minutes
            if time.time() - cache_time < 300:
                return cached_path

    # Perform path resolution
    rclone_path = Path(settings_manager.settings.symlink.rclone_path)

    # Optimize folder list creation
    possible_folders = []
    if item.folder:
        possible_folders.append(item.folder)
    if hasattr(item, 'alternative_folder') and item.alternative_folder:
        possible_folders.append(item.alternative_folder)

    # Remove duplicates while preserving order
    seen = set()
    unique_folders = []
    for folder in possible_folders:
        if folder and folder not in seen:
            seen.add(folder)
            unique_folders.append(folder)

    # Add stem version if we only have one folder
    if len(unique_folders) == 1:
        stem_folder = Path(unique_folders[0]).with_suffix("")
        if str(stem_folder) not in seen:
            unique_folders.append(stem_folder)

    # Search for file in folders (most likely locations first)
    result_path = None
    for folder in unique_folders:
        file_path = rclone_path / folder / item.file
        if file_path.exists():
            result_path = file_path
            break

    # Fallback: check root directory
    if not result_path:
        root_file = rclone_path / item.file
        if root_file.exists() and root_file.is_file():
            result_path = root_file

    # Cache the result
    with _path_cache_lock:
        _path_resolution_cache[cache_key] = (result_path, time.time())

        # Limit cache size to prevent memory issues
        if len(_path_resolution_cache) > _path_cache_max_size:
            # Remove oldest 20% of entries
            oldest_keys = sorted(_path_resolution_cache.keys(),
                               key=lambda k: _path_resolution_cache[k][1])[:200]
            for key in oldest_keys:
                del _path_resolution_cache[key]

    return result_path