import asyncio
import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from sqlalchemy import select

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from program.media.stream import Stream
from program.db.db import db
from utils.logger import logger


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

    def run(self, item: Union[Movie, Show, Season, Episode]):
        """Check if the media item exists and create a symlink if it does"""
        try:
            if isinstance(item, Show):
                self._symlink_show(item)
            elif isinstance(item, Season):
                self._symlink_season(item)
            elif isinstance(item, (Movie, Episode)):
                self._symlink_single(item)
        except Exception as e:
            logger.error(f"Exception thrown when creating symlink for {item.log_string}: {e}")

        item.set("symlinked_times", item.symlinked_times + 1)
        yield item

    @staticmethod
    def should_submit(item: Union[Movie, Show, Season, Episode]) -> bool:
        """Check if the item should be submitted for symlink creation."""
        if not item:
            logger.error("Invalid item sent to Symlinker: None")
            return False

        if isinstance(item, Show):
            all_episodes_ready = True
            for season in item.seasons:
                for episode in season.episodes:
                    if not episode.file or not episode.folder or episode.file == "None.mkv":
                        logger.warning(f"Cannot submit {episode.log_string} for symlink: Invalid file or folder. Needs to be rescraped.")
                        all_episodes_ready = False
                    elif not quick_file_check(episode):
                        logger.debug(f"File not found for {episode.log_string} at the moment, waiting for it to become available")
                        if not _wait_for_file(episode):
                            all_episodes_ready = False
                            break  # Give up on the whole season if one episode is not found in 90 seconds
            if not all_episodes_ready:
                logger.warning(f"Cannot submit show {item.log_string} for symlink: One or more episodes need to be rescraped.")
            return all_episodes_ready

        if isinstance(item, Season):
            all_episodes_ready = True
            for episode in item.episodes:
                if not episode.file or not episode.folder or episode.file == "None.mkv":
                    logger.warning(f"Cannot submit {episode.log_string} for symlink: Invalid file or folder. Needs to be rescraped.")
                    all_episodes_ready = False
                elif not quick_file_check(episode):
                    logger.debug(f"File not found for {episode.log_string} at the moment, waiting for it to become available")
                    if not _wait_for_file(episode):
                        all_episodes_ready = False
                        break  # Give up on the whole season if one episode is not found in 90 seconds
            if not all_episodes_ready:
                logger.warning(f"Cannot submit season {item.log_string} for symlink: One or more episodes need to be rescraped.")
            return all_episodes_ready

        if isinstance(item, (Movie, Episode)):
            if not item.file or not item.folder or item.file == "None.mkv":
                logger.warning(f"Cannot submit {item.log_string} for symlink: Invalid file or folder. Needs to be rescraped.")
                return False

        if item.symlinked_times < 3:
            if quick_file_check(item):
                logger.log("SYMLINKER", f"File found for {item.log_string}, submitting to be symlinked")
                return True
            else:
                logger.debug(f"File not found for {item.log_string} at the moment, waiting for it to become available")
                if _wait_for_file(item):
                    return True
                return False

        item.set("symlinked_times", item.symlinked_times + 1)

        if item.symlinked_times >= 3:
            rclone_path = Path(settings_manager.settings.symlink.rclone_path)
            if search_file(rclone_path, item):
                logger.log("SYMLINKER", f"File found for {item.log_string}, creating symlink")
                return True
            else:
                logger.log("SYMLINKER", f"File not found for {item.log_string} after 3 attempts, skipping")
                return False

        logger.debug(f"Item {item.log_string} not submitted for symlink, file not found yet")
        return False

    def _symlink_show(self, show: Show):
        if not show or not isinstance(show, Show):
            logger.error(f"Invalid show sent to Symlinker: {show}")
            return

        all_symlinked = True
        for season in show.seasons:
            for episode in season.episodes:
                if not episode.symlinked and episode.file and episode.folder:
                    if self._symlink(episode):
                        episode.set("symlinked", True)
                        episode.set("symlinked_at", datetime.now())
                    else:
                        all_symlinked = False
        if all_symlinked:
            logger.log("SYMLINKER", f"Symlinked all episodes for show {show.log_string}")
        else:
            logger.error(f"Failed to symlink some episodes for show {show.log_string}")

    def _symlink_season(self, season: Season):
        if not season or not isinstance(season, Season):
            logger.error(f"Invalid season sent to Symlinker: {season}")
            return

        all_symlinked = True
        successfully_symlinked_episodes = []
        for episode in season.episodes:
            if not episode.symlinked and episode.file and episode.folder:
                if self._symlink(episode):
                    episode.set("symlinked", True)
                    episode.set("symlinked_at", datetime.now())
                    successfully_symlinked_episodes.append(episode)
                else:
                    all_symlinked = False
        if all_symlinked:
            logger.log("SYMLINKER", f"Symlinked all episodes for {season.log_string}")
        else:
            for episode in successfully_symlinked_episodes:
                logger.log("SYMLINKER", f"Symlink created for {episode.log_string}")

    def _symlink_single(self, item: Union[Movie, Episode]):
        if not item.symlinked and item.file and item.folder:
            if self._symlink(item):
                logger.log("SYMLINKER", f"Symlink created for {item.log_string}")

    def _symlink(self, item: Union[Movie, Episode]) -> bool:
        """Create a symlink for the given media item if it does not already exist."""
        if not item:
            logger.error("Invalid item sent to Symlinker: None")
            return False

        if item.file is None:
            logger.error(f"Item file is None for {item.log_string}, cannot create symlink.")
            return False

        if not item.folder:
            logger.error(f"Item folder is None for {item.log_string}, cannot create symlink.")
            return False

        filename = self._determine_file_name(item)
        if not filename:
            logger.error(f"Symlink filename is None for {item.log_string}, cannot create symlink.")
            return False

        extension = os.path.splitext(item.file)[1][1:]
        symlink_filename = f"{filename}.{extension}"
        destination = self._create_item_folders(item, symlink_filename)
        source = os.path.join(self.rclone_path, item.folder, item.file)

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

        if os.readlink(destination) != source:
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
            episode_number: List[int] = item.get_file_episodes()
            if episode_number and item.number in episode_number:
                if len(episode_number) > 1:
                    episode_string = f"e{str(episode_number[0]).zfill(2)}-e{str(episode_number[-1]).zfill(2)}"
                else:
                    episode_string = f"e{str(item.number).zfill(2)}"
            if episode_string != "":
                showname = item.parent.parent.title
                showyear = item.parent.parent.aired_at.year
                filename = f"{showname} ({showyear}) - s{str(item.parent.number).zfill(2)}{episode_string} - {item.title}"
        return filename

    def delete_item_symlinks(self, id: int) -> bool:
        """Delete symlinks and directories based on the item type."""
        with db.Session() as session:
            item = session.execute(select(MediaItem).where(MediaItem._id == id)).unique().scalar_one_or_none()
            if not item:
                logger.error(f"Item with id {id} not found")
                return False

            try:
                if isinstance(item, Show):
                    base_path = self.library_path_anime_shows if item.is_anime else self.library_path_shows
                    item_path = base_path / f"{item.title.replace('/', '-')} ({item.aired_at.year}) {{imdb-{item.imdb_id}}}"
                elif isinstance(item, Season):
                    show = item.parent
                    base_path = self.library_path_anime_shows if show.is_anime else self.library_path_shows
                    item_path = base_path / f"{show.title.replace('/', '-')} ({show.aired_at.year}) {{imdb-{show.imdb_id}}}" / f"Season {str(item.number).zfill(2)}"
                elif isinstance(item, Episode):
                    show = item.parent.parent
                    season = item.parent
                    base_path = self.library_path_anime_shows if show.is_anime else self.library_path_shows
                    if item.file:
                        item_path = base_path / f"{show.title.replace('/', '-')} ({show.aired_at.year}) {{imdb-{show.imdb_id}}}" / f"Season {str(season.number).zfill(2)}" / f"{self._determine_file_name(item)}.{os.path.splitext(item.file)[1][1:]}"
                    else:
                        logger.error(f"File attribute is None for {item.log_string}, cannot determine path.")
                        return False
                elif isinstance(item, Movie):
                    base_path = self.library_path_anime_movies if item.is_anime else self.library_path_movies
                    if item.file:
                        item_path = base_path / f"{self._determine_file_name(item)}.{os.path.splitext(item.file)[1][1:]}"
                    else:
                        logger.error(f"File attribute is None for {item.log_string}, cannot determine path.")
                        return False
                else:
                    logger.error(f"Unsupported item type for deletion: {type(item)}")
                    return False

                if item_path.exists():
                    if item_path.is_dir():
                        shutil.rmtree(item_path)
                    else:
                        item_path.unlink()
                    logger.debug(f"Deleted symlink for {item.log_string}")

                    if isinstance(item, (Movie, Episode)):
                        item.reset(True)
                    elif isinstance(item, Show):
                        for season in item.seasons:
                            for episode in season.episodes:
                                episode.reset(True)
                            season.reset(True)
                        item.reset(True)
                    elif isinstance(item, Season):
                        for episode in item.episodes:
                            episode.reset(True)
                        item.reset(True)

                    item.store_state()
                    session.commit()

                    logger.debug(f"Item reset to be rescraped: {item.log_string}")
                    return True
                else:
                    logger.error(f"Symlink path does not exist for {item.log_string}")
            except FileNotFoundError as e:
                logger.error(f"File not found error when deleting symlink for {item.log_string}: {e}")
            except PermissionError as e:
                logger.error(f"Permission denied when deleting symlink for {item.log_string}: {e}")
            except Exception as e:
                logger.error(f"Failed to delete symlink for {item.log_string}, error: {e}")
            return False


def _wait_for_file(item: Union[Movie, Episode], timeout: int = 90) -> bool:
    """Wrapper function to run the asynchronous wait_for_file function."""
    return asyncio.run(wait_for_file(item, timeout))

async def wait_for_file(item: Union[Movie, Episode], timeout: int = 90) -> bool:
    """Asynchronously wait for the file to become available within the given timeout."""
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        # keep trying to find the file until timeout duration is hit
        if quick_file_check(item):
            logger.log("SYMLINKER", f"File found for {item.log_string}")
            return True
        await asyncio.sleep(5)
        # If 30 seconds have passed, try searching for the file
        if time.monotonic() - start_time >= 30:
            rclone_path = Path(settings_manager.settings.symlink.rclone_path)
            if search_file(rclone_path, item):
                logger.log("SYMLINKER", f"File found for {item.log_string} after searching")
                return True
    logger.log("SYMLINKER", f"File not found for {item.log_string} after waiting for {timeout} seconds, skipping")
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

    if item.symlinked_times >= 3:
        item.reset()
        logger.log("SYMLINKER", f"Reset item {item.log_string} back to scrapable after 3 failed attempts")

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
