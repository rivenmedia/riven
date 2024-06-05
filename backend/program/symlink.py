import contextlib
import os
from datetime import datetime
from pathlib import Path
import time
from typing import Union
from concurrent.futures import ThreadPoolExecutor
import threading

from program.media.item import Episode, Movie, Season, Show
from program.settings.manager import settings_manager
from utils.logger import logger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .cache import hash_cache

symlink_pool = ThreadPoolExecutor(max_workers=10)

class DeleteHandler(FileSystemEventHandler):
    """Handles the deletion of symlinks."""

    def __init__(self, symlinker):
        super().__init__()
        self.symlinker = symlinker

    def on_deleted(self, event):
        """Called when a file or directory is deleted."""
        if event.src_path:
            self.symlinker.on_symlink_deleted(event.src_path)


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
        # we can't delete from rclone if this is enabled
        self.torbox_enabled = settings_manager.settings.downloaders.torbox.enabled
        self.rclone_path = self.settings.rclone_path
        self.initialized = self.validate()
        if not self.initialized:
            logger.error("Symlink initialization failed due to invalid configuration.")
            return
        if self.initialized:
            self.start_monitor()
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
        if not self.rclone_path.is_absolute():
            logger.error(f"rclone_path is not an absolute path: {self.rclone_path}")
            return False
        if not library_path.is_absolute():
            logger.error(f"library_path is not an absolute path: {library_path}")
            return False
        if not self.rclone_path.exists():
            logger.error(f"rclone_path does not exist: {self.rclone_path}")
            return False
        if not library_path.exists():
            logger.error(f"library_path does not exist: {library_path}")
            return False
        return self.create_initial_folders()

    def create_initial_folders(self):
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

    def run(self, item: Union[Movie, Episode]):
        """Check if the media item exists and create a symlink if it does"""
        try:
            if self._symlink(item):
                item.set("symlinked", True)
                item.set("symlinked_at", datetime.now())
                logger.log("SYMLINKER", f"Symlink created for {item.log_string}")
            else:
                logger.error(f"Failed to create symlink for {item.log_string}")
        except Exception as e:
            logger.exception(f"Exception thrown when creating symlink for {item.log_string}: {e}")

        item.set("symlinked_times", item.symlinked_times + 1)
        yield item

    @staticmethod
    def should_submit(item: Union[Movie, Episode]) -> bool:
        """Check if the item should be submitted for symlink creation."""
        if isinstance(item, Show):
            return False

        logger.debug(f"Checking if {item.log_string} should be submitted for symlink")

        if isinstance(item, Season):
            # Skip episodes that aren't set
            if not any(ep.file and ep.folder for ep in item.episodes):
                logger.debug(f"Skipping season {item.log_string} as no episodes have file and folder set")
                return False
        
        if isinstance(item, (Movie, Episode)):
            if not item.file or not item.folder or item.file == "None.mkv":
                logger.error(f"Cannot submit {item.log_string} for symlink: Invalid file or folder. Needs to be rescraped.")
                Symlinker.blacklist_item(item)
                return False

        if item.symlinked_times < 3:
            if quick_file_check(item):
                logger.log("SYMLINKER", f"File found for {item.log_string} after waiting, resubmitting")
                return True
            else:
                logger.debug(f"File not found for {item.log_string}, will retry")
                symlink_pool.submit(_wait_for_file, item, Symlinker)
                return False

        item.set("symlinked_times", item.symlinked_times + 1)

        if item.symlinked_times == 3:
            rclone_path = Path(settings_manager.settings.symlink.rclone_path)
            if search_file(rclone_path, item):
                logger.log("SYMLINKER", f"File found for {item.log_string}, creating symlink")
                return True
            else:
                logger.log("SYMLINKER", f"File not found for {item.log_string} after 3 attempts, blacklisting")
                Symlinker.blacklist_item(item)

        logger.debug(f"Item {item.log_string} not submitted for symlink, file not found yet")
        return False

    def _symlink(self, item: Union[Movie, Episode]) -> bool:
        """Create a symlink for the given media item if it does not already exist."""
        extension = os.path.splitext(item.file)[1][1:]
        symlink_filename = f"{self._determine_file_name(item)}.{extension}"
        destination = self._create_item_folders(item, symlink_filename)
        source = os.path.join(self.rclone_path, item.folder, item.file)

        if not os.path.exists(source):
            logger.error(f"Source file does not exist: {source}")
            return False

        try:
            with contextlib.suppress(FileExistsError):
                os.symlink(source, destination)
            item.set("symlinked", True)
            item.set("symlinked_at", datetime.now())
            item.set("symlinked_times", item.symlinked_times + 1)
        except PermissionError as e:
            logger.error(f"Permission denied when creating symlink for {item.log_string}: {e}")
            return False
        except OSError as e:
            logger.error(f"OS error when creating symlink for {item.log_string}: {e}")
            return False

        return True

    def _create_item_folders(self, item: Union[Movie, Season, Episode], filename: str) -> str:
        """Create necessary folders and determine the destination path for symlinks."""
        if isinstance(item, Movie):
            movie_folder = (
                f"{item.title.replace('/', '-')} ({item.aired_at.year}) "
                + "{imdb-"
                + item.imdb_id
                + "}"
            )
            destination_folder = os.path.join(self.library_path_movies, movie_folder)
            if not os.path.exists(destination_folder):
                os.mkdir(destination_folder)
            destination_path = os.path.join(
                destination_folder, filename.replace("/", "-")
            )
            item.set("update_folder", os.path.join(self.library_path_movies, movie_folder))
        elif isinstance(item, Season):
            show = item.parent
            folder_name_show = (
                f"{show.title.replace('/', '-')} ({show.aired_at.year})"
                + " {"
                + show.imdb_id
                + "}"
            )
            show_path = os.path.join(self.library_path_shows, folder_name_show)
            os.makedirs(show_path, exist_ok=True)
            folder_season_name = f"Season {str(item.number).zfill(2)}"
            season_path = os.path.join(show_path, folder_season_name)
            os.makedirs(season_path, exist_ok=True)
            destination_path = os.path.join(season_path, filename.replace("/", "-"))
            item.set("update_folder", os.path.join(season_path))
        elif isinstance(item, Episode):
            show = item.parent.parent
            folder_name_show = (
                f"{show.title.replace('/', '-')} ({show.aired_at.year})"
                + " {"
                + show.imdb_id
                + "}"
            )
            show_path = os.path.join(self.library_path_shows, folder_name_show)
            os.makedirs(show_path, exist_ok=True)
            season = item.parent
            folder_season_name = f"Season {str(season.number).zfill(2)}"
            season_path = os.path.join(show_path, folder_season_name)
            os.makedirs(season_path, exist_ok=True)
            destination_path = os.path.join(season_path, filename.replace("/", "-"))
            item.set("update_folder", os.path.join(season_path))
        return destination_path

    def start_monitor(self):
        """Starts monitoring the library path for symlink deletions."""
        self.event_handler = DeleteHandler(self)
        self.observer = Observer()
        self.observer.schedule(
            self.event_handler, self.settings.library_path, recursive=True
        )
        self.observer.start()
        logger.log("FILES", "Symlink deletion monitoring started")

    def stop_monitor(self):
        """Stops the directory monitoring."""
        if hasattr(self, "observer"):
            self.observer.stop()
            self.observer.join()
            logger.log("FILES", "Stopped monitoring for symlink deletions")

    def on_symlink_deleted(self, symlink_path):
        """Handle a symlink deletion event."""
        src = Path(symlink_path)
        if src.is_symlink():
            dst = src.resolve()
            logger.log("FILES", f"Symlink deleted: {src} -> {dst}")
        else:
            logger.log("FILES", f"Symlink deleted: {src} (target unknown)")
        # TODO: Implement logic to handle deletion..

    def _determine_file_name(self, item) -> str | None:
        """Determine the filename of the symlink."""
        filename = None
        if isinstance(item, Movie):
            filename = f"{item.title} ({item.aired_at.year}) " + "{imdb-" + item.imdb_id + "}"
        elif isinstance(item, Season):
            showname = item.parent.title
            showyear = item.parent.aired_at.year
            filename = f"{showname} ({showyear}) - Season {str(item.number).zfill(2)}"
        elif isinstance(item, Episode):
            episode_string = ""
            episode_number = item.get_file_episodes()
            if episode_number[0] == item.number:
                if len(episode_number) > 1:
                    episode_string = f"e{str(episode_number[0]).zfill(2)}-e{str(episode_number[-1]).zfill(2)}"
                else:
                    episode_string = f"e{str(item.number).zfill(2)}"
            if episode_string != "":
                showname = item.parent.parent.title
                showyear = item.parent.parent.aired_at.year
                filename = f"{showname} ({showyear}) - s{str(item.parent.number).zfill(2)}{episode_string} - {item.title}" 
        return filename


def _wait_for_file(item: Union[Movie, Episode], symlinker: Symlinker, timeout: int = 60) -> bool:
    """Wait for the file to become available within the given timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if quick_file_check(item):
            symlinker.run(item)
            return True
        time.sleep(5)
    logger.log("SYMLINKER", f"File not found for {item.log_string} after waiting for {timeout} seconds, blacklisting")
    Symlinker.blacklist_item(item)
    return False

def quick_file_check(item: Union[Movie, Episode]) -> bool:
    """Quickly check if the file exists in the rclone path."""
    if not isinstance(item, (Movie, Episode)):
        logger.debug(f"Cannot create symlink for {item.log_string}: Not a movie or episode")
        return False

    if not item.file or item.file == "None.mkv":
        logger.log("NOT_FOUND", f"Invalid file for {item.log_string}: {item.file}. Needs to be rescraped.")
        return False

    rclone_path = Path(settings_manager.settings.symlink.rclone_path)
    possible_folders = [item.folder, item.file, item.alternative_folder]

    for folder in possible_folders:
        if folder:
            file_path = rclone_path / folder / item.file
            if file_path.exists():
                item.set("folder", folder)
                return True
    return False

def search_file(rclone_path: Path, item: Union[Movie, Episode]) -> bool:
    """Search for the file in the rclone path."""
    if not isinstance(item, (Movie, Episode)):
        logger.debug(f"Cannot search for file for {item.log_string}: Not a movie or episode")
        return False

    filename = item.file
    if not filename:
        return False
    logger.debug(f"Searching for file {filename} in {rclone_path}")
    try:
        for root, _, files in os.walk(rclone_path):
            if filename in files:
                relative_root = Path(root).relative_to(rclone_path).as_posix()
                item.set("folder", relative_root)
                return True
        logger.debug(f"File {filename} not found in {rclone_path}")
    except Exception as e:
        logger.error(f"Error occurred while searching for file {filename} in {rclone_path}: {e}")
    return False

@staticmethod
def blacklist_item(item):
    """Blacklist the item and reset its attributes."""
    infohash = Symlinker.get_infohash(item)
    Symlinker.reset_item(item)
    if infohash:
        hash_cache.blacklist(infohash)
    else:
        logger.error(f"Failed to retrieve hash for {item.log_string}, unable to blacklist")

@staticmethod
def reset_item(item):
    """Reset item attributes for rescraping."""
    item.set("file", None)
    item.set("folder", None)
    item.set("streams", {})
    item.set("active_stream", {})
    item.set("symlinked_times", 0)
    logger.debug(f"Item {item.log_string} reset for rescraping")

@staticmethod
def get_infohash(item):
    """Retrieve the infohash from the item or its parent."""
    infohash = item.active_stream.get("hash")
    if isinstance(item, Episode) and not infohash:
        infohash = item.parent.active_stream.get("hash")
    if isinstance(item, Movie) and not infohash:
        logger.error(f"Failed to retrieve hash for {item.log_string}, unable to blacklist")
    return infohash