"""Symlinking module"""
import os
import threading
import time
from utils.settings import settings_manager as settings
from utils.logger import logger


class Symlinker(threading.Thread):
    """
    A class that represents a symlinker thread.

    Attributes:
        media_items (MediaItemContainer): The container of media items.
        running (bool): Flag indicating if the thread is running.
        cache (dict): A dictionary to cache file paths.
        mount_path (str): The absolute path of the container mount.
        host_path (str): The absolute path of the host mount.
        symlink_path (str): The path where the symlinks will be created.
        cache_thread (ThreadRunner): The thread runner for updating the cache.
    """

    def __init__(self):
        # Symlinking is required
        super().__init__(name="Symlinker")

        while True:
            self.mount_path = os.path.abspath(settings.get("container_mount"))
            self.host_path = os.path.abspath(settings.get("host_mount"))
            if os.path.exists(self.host_path):
                self.symlink_path = os.path.join(self.host_path, os.pardir, "library")
                if not os.path.exists(self.symlink_path):
                    os.mkdir(self.symlink_path)
                if not os.path.exists(os.path.join(self.symlink_path, "movies")):
                    os.mkdir(os.path.join(self.symlink_path, "movies"))
                if not os.path.exists(os.path.join(self.symlink_path, "shows")):
                    os.mkdir(os.path.join(self.symlink_path, "shows"))
                break
            else:
                logger.error("Rclone mount not found, retrying in 2...")
                time.sleep(2)

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
        if os.path.exists(os.path.join(self.host_path, item.folder, item.file)):
            self._symlink(item)

    def _symlink(self, item):
        extension = item.file.split(".")[-1]
        symlink_filename = f"{self._determine_file_name(item)}.{extension}"

        if item.type == "movie":
            movie_folder = (
                f"{item.title} ({item.aired_at.year}) "
                + "{imdb-"
                + item.imdb_id
                + "}"
            )
            symlink_folder_path = os.path.join(
                self.symlink_path, "movies", movie_folder
            )
            if not os.path.exists(symlink_folder_path):
                os.mkdir(symlink_folder_path)
            symlink_path = os.path.join(symlink_folder_path, symlink_filename)
            update_folder = os.path.join(
                self.mount_path, os.pardir, "library", "movies", movie_folder
            )
        if item.type == "episode":
            show = item.parent.parent
            symlink_show_folder = (
                f"{show.title} ({show.aired_at.year})" + " {" + show.imdb_id + "}"
            )
            symlink_show_path = os.path.join(
                self.symlink_path, "shows", symlink_show_folder
            )
            if not os.path.exists(symlink_show_path):
                os.mkdir(symlink_show_path)
            season = item.parent
            symlink_season_folder = f"Season {str(season.number).zfill(2)}"
            season_path = os.path.join(symlink_show_path, symlink_season_folder)
            if not os.path.exists(season_path):
                os.mkdir(season_path)
            symlink_path = os.path.join(season_path, symlink_filename)
            update_folder = os.path.join(
                self.mount_path,
                os.pardir,
                "library",
                "shows",
                symlink_show_folder,
                symlink_season_folder,
            )

        if symlink_path:
            try:
                os.remove(symlink_path)
            except FileNotFoundError:
                pass
            os.symlink(
                os.path.join(self.mount_path, item.folder, item.file), symlink_path
            )
            item.set("update_folder", update_folder)
            log_string = item.title
            if item.type == "episode":
                log_string = f"{item.parent.parent.title} season {item.parent.number} episode {item.number}"
            logger.debug("Created symlink for %s", log_string)
            item.symlinked = True

symlink = Symlinker()