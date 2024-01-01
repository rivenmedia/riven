"""Symlinking module"""
import os
import threading
import time
from typing import Optional

from pydantic import BaseModel
from utils.settings import settings_manager as settings
from utils.logger import logger


class SymlinkConfig(BaseModel):
    host_path: Optional[str]
    container_path: Optional[str]


class Symlinker(threading.Thread):
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

    def __init__(self):
        # Symlinking is required
        super().__init__(name="Symlinker")
        self.key = "symlink"
        self.settings = SymlinkConfig(**settings.get(self.key))

        while True:
            self.library_path = os.path.join(
                os.path.dirname(self.settings.host_path), "library"
            )
            self.library_path_movies = os.path.join(self.library_path, "movies")
            self.library_path_shows = os.path.join(self.library_path, "shows")
            if os.path.exists(self.settings.host_path):
                self._create_init_folders()
                break
            else:
                logger.error("Rclone mount not found, retrying in 2...")
                time.sleep(2)

    def _create_init_folders(self):
        movies = os.path.join(self.library_path_movies)
        shows = os.path.join(self.library_path_shows)
        if not os.path.exists(self.library_path):
            os.mkdir(self.library_path)
        if not os.path.exists(movies):
            os.mkdir(movies)
        if not os.path.exists(shows):
            os.mkdir(shows)

    def run(self, item):
        self._run(item)

    def _determine_file_name(self, item):
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
        if os.path.exists(
            os.path.join(self.settings.host_path, item.folder, item.file)
        ):
            self._symlink(item)

    def _symlink(self, item):
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
            log_string = item.title
            if item.type == "episode":
                log_string = f"{item.parent.parent.title} season {item.parent.number} episode {item.number}"
            logger.debug("Created symlink for %s", log_string)
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
                f"{item.title} ({item.aired_at.year}) " + "{imdb-" + item.imdb_id + "}"
            )
            destination_folder = os.path.join(self.library_path_movies, movie_folder)
            if not os.path.exists(destination_folder):
                os.mkdir(destination_folder)
            destination_path = os.path.join(destination_folder, filename)
            item.set(
                "update_folder", os.path.join(self.library_path_movies, movie_folder)
            )
        if item.type == "episode":
            show = item.parent.parent
            folder_name_show = (
                f"{show.title} ({show.aired_at.year})" + " {" + show.imdb_id + "}"
            )
            show_path = os.path.join(self.library_path_shows, folder_name_show)
            if not os.path.exists(show_path):
                os.mkdir(show_path)
            season = item.parent
            folder_season_name = f"Season {str(season.number).zfill(2)}"
            season_path = os.path.join(show_path, folder_season_name)
            if not os.path.exists(season_path):
                os.mkdir(season_path)
            destination_path = os.path.join(season_path, filename)
            item.set("update_folder", os.path.join(season_path))
        return destination_path
