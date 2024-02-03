"""Symlinking module"""
import os
from pathlib import Path
from typing import NamedTuple
from pydantic import BaseModel
from utils.settings import settings_manager as settings
from utils.logger import logger


class SymlinkConfig(BaseModel):
    host_path: Path
    container_path: Path

class Setting(NamedTuple):
    key: str
    value: str

class Symlinker():
    """
    A class that represents a symlinker thread.

    Attributes:
        media_items (MediaItemContainer): The container of media items.
        running (bool): Flag indicating if the thread is running.
        cache (dict): A dictionary to cache file paths.
        container_path (str): The absolute path of the container mount.
        host_path (str): The absolute path of the host mount.
        symlink_path (str): The path where the symlinks will be created.
    """
    def __init__(self, _):
        self.key = "symlink"
        self.settings = SymlinkConfig(**settings.get(self.key))
        self.initialized = self.validate()
        if not self.initialized:
            logger.error("Symlink initialization failed due to invalid configuration.")
            return
        logger.info("Rclone path symlinks are pointed to: %s", self.settings.host_path)
        logger.info("Symlinks will be placed in: %s", self.library_path)
        logger.info("Symlink initialized!")
        self.initialized = True

    def validate(self):
        """Validate paths and create the initial folders."""
        host_path = Path(self.settings.host_path) if self.settings.host_path else None
        container_path = Path(self.settings.container_path) if self.settings.container_path else None
        if not host_path or not container_path or host_path == Path('.') or container_path == Path('.'):
            logger.error("Host or container path not provided, is empty, or is set to the current directory.")
            return False
        if not host_path.is_absolute():
            logger.error(f"Host path is not an absolute path: {host_path}")
            return False
        if not container_path.is_absolute():
            logger.error(f"Container path is not an absolute path: {container_path}")
            return False
        try:
            if not host_path.is_dir():
                logger.error(f"Host path is not a directory or does not exist: {host_path}")
                return False
            if not container_path.is_dir():
                logger.error(f"Container path is not a directory or does not exist: {container_path}")
                return False
            if Path(self.settings.host_path / "__all__").exists() and Path(self.settings.host_path / "__all__").is_dir():
                logger.debug("Detected Zurg host path. Using __all__ folder for host path.")
                self.settings.host_path = self.settings.host_path / "__all__"
            elif Path(self.settings.host_path / "torrents").exists() and Path(self.settings.host_path / "torrents").is_dir():
                logger.debug("Detected standard rclone host path. Using torrents folder for host path.")
                self.settings.host_path = self.settings.host_path / "torrents"
            if not self.create_initial_folders():
                logger.error("Failed to create initial library folders.")
                return False
            return True
        except FileNotFoundError as e:
            logger.error(f"Path not found: {e}")
        except PermissionError as e:
            logger.error(f"Permission denied when accessing path: {e}")
        except OSError as e:
            logger.error(f"OS error when validating paths: {e}")
        return False

    def create_initial_folders(self):
        """Create the initial library folders."""
        try:
            self.library_path = self.settings.container_path.parent / "library"
            self.library_path_movies = self.library_path / "movies"
            self.library_path_shows = self.library_path / "shows"
            self.library_path_anime_movies = self.library_path / "anime_movies"
            self.library_path_anime_shows = self.library_path / "anime_shows"
            folders = [self.library_path_movies, 
                    self.library_path_shows, 
                    self.library_path_anime_movies, 
                    self.library_path_anime_shows]
            for folder in folders:
                if not folder.exists():
                    folder.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            logger.error(f"Permission denied when creating directory: {e}")
            return False
        except OSError as e:
            logger.error(f"OS error when creating directory: {e}")
            return False
        return True

    def run(self, item):
        self._run(item)

    def _determine_file_name(self, item):
        """Determine the filename of the symlink."""
        filename = None
        if item.type == "movie":
            filename = (
                f"{item.title} ({item.aired_at.year}) " + "{imdb-" + item.imdb_id + "}"
            )
        if item.type == "episode":
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

    def _run(self, item):
        """Check if the media item exists and create a symlink if it does"""
        found = False
        if os.path.exists(os.path.join(self.settings.host_path, item.folder, item.file)):
            found = True
        elif os.path.exists(os.path.join(self.settings.host_path, item.alternative_folder, item.file)):
            item.set("folder", item.alternative_folder)
            found = True
        elif os.path.exists(os.path.join(self.settings.host_path, item.file, item.file)):
            item.set("folder", item.file)
            found = True
        if found:
            self._symlink(item)

    def _symlink(self, item):
        """Create a symlink for the given media item"""
        extension = item.file.split(".")[-1]
        symlink_filename = f"{self._determine_file_name(item)}.{extension}"

        destination = self._create_item_folders(item, symlink_filename)

        if destination:
            try:
                os.remove(destination)
            except FileNotFoundError:
                pass
            os.symlink(
                os.path.join(self.settings.container_path, item.folder, item.file),
                destination,
            )
            logger.debug("Created symlink for %s", item.log_string)
            item.symlinked = True
        else:
            logger.debug(
                "Could not create symlink for item_id (%s) to (%s)",
                item.id,
                destination,
            )

    def _create_item_folders(self, item, filename) -> str:
        if item.type == "movie":
            movie_folder = (
                f"{item.title.replace('/', '-')} ({item.aired_at.year}) " + "{imdb-" + item.imdb_id + "}"
            )
            destination_folder = os.path.join(self.library_path_movies, movie_folder)
            if not os.path.exists(destination_folder):
                os.mkdir(destination_folder)
            destination_path = os.path.join(destination_folder, filename.replace('/', '-'))
            item.set(
                "update_folder", os.path.join(self.library_path_movies, movie_folder)
            )
        if item.type == "episode":
            show = item.parent.parent
            folder_name_show = (
                f"{show.title.replace('/', '-')} ({show.aired_at.year})" + " {" + show.imdb_id + "}"
            )
            show_path = os.path.join(self.library_path_shows, folder_name_show)
            if not os.path.exists(show_path):
                os.mkdir(show_path)
            season = item.parent
            folder_season_name = f"Season {str(season.number).zfill(2)}"
            season_path = os.path.join(show_path, folder_season_name)
            if not os.path.exists(season_path):
                os.mkdir(season_path)
            destination_path = os.path.join(season_path, filename.replace('/', '-'))
            item.set("update_folder", os.path.join(season_path))
        return destination_path
