"""Symlinking module"""
import os
import threading
import time
import PTN
from utils.settings import settings_manager as settings
from utils.logger import logger
from program.media import MediaItemState, MediaItemContainer
from utils.thread import ThreadRunner


class Symlinker(threading.Thread):
    """Content class for mdblist"""

    def __init__(self, media_items: MediaItemContainer):
        # Symlinking is required
        super().__init__(name="Symlinker")

        while True:
            self.running = False
            self.media_items = media_items
            self.cache = {}
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
        if self.host_path:
            self.cache_thread = ThreadRunner(self.update_cache, 10)
            self.cache_thread.start()

    def run(self):
        while self.running:
            self._run()

    def start(self):
        self.running = True
        super().start()

    def stop(self):
        self.running = False
        self.cache_thread.stop()
        super().join()

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

    def _run(self):
        items = []
        for item in self.media_items:
            if item.type == "movie" and item.state is MediaItemState.DOWNLOAD:
                item.set(
                    "file",
                    next(iter(item.active_stream["files"].values())).get("filename"),
                )
                file = self._find_file(item.file)
                if file:
                    item.set("folder", os.path.dirname(file).split("/")[-1])
                    items.append(item)
            if item.type == "show":
                for season in item.seasons:
                    if season.state is MediaItemState.DOWNLOAD:
                        stream = season.get("active_stream")
                        if stream:
                            for file in season.active_stream["files"].values():
                                obj = PTN.parse(file["filename"])
                                if not obj.get("episode"):
                                    continue
                                episode = obj["episode"]
                                if type(episode) == list:
                                    for sub_episode in episode:
                                        if sub_episode - 1 in range(len(season.episodes)):
                                            season.episodes[sub_episode - 1].set(
                                                "file", file["filename"]
                                            )
                                else:
                                    index = obj["episode"] - 1
                                    if index in range(len(season.episodes)):
                                        season.episodes[obj["episode"] - 1].set(
                                            "file", file["filename"]
                                        )
                        for episode in season.episodes:
                            if episode.state is MediaItemState.DOWNLOAD:
                                file = self._find_file(episode.file)
                                if file:
                                    episode.set(
                                        "folder", os.path.dirname(file).split("/")[-1]
                                    )
                                    items.append(episode)
                    else:
                        for episode in season.episodes:
                            if episode.state is MediaItemState.DOWNLOAD:
                                stream = episode.get("active_stream")
                                if stream:
                                    for file in episode.active_stream["files"].values():
                                        obj = PTN.parse(file["filename"])
                                        if not obj.get("episode"):
                                            continue
                                        episode_number = obj["episode"]
                                        if type(episode_number) == list:
                                            if episode.number in episode_number:
                                                episode.set("file", file["filename"])
                                        else:
                                            if episode.number == episode_number:
                                                episode.set("file", file["filename"])
                                        file = self._find_file(episode.file)
                                        if file:
                                            episode.set(
                                                "folder",
                                                os.path.dirname(file).split("/")[-1],
                                            )
                                            items.append(episode)

        for item in items:
            extension = item.file.split(".")[-1]
            symlink_filename = f"{self._determine_file_name(item)}.{extension}"

            if item.type == "movie":
                movie_folder = (
                    f"{item.title} ({item.aired_at.year}) "
                    + "{imdb-"
                    + item.imdb_id
                    + "}"
                )
                folder_path = os.path.join(self.symlink_path, "movies", movie_folder)
                symlink_path = os.path.join(folder_path, symlink_filename)
                if not os.path.exists(folder_path):
                    os.mkdir(folder_path)
                update_folder = os.path.join(
                    self.mount_path, os.pardir, "library", "movies", movie_folder
                )
            if item.type == "episode":
                show = item.parent.parent
                show_folder = (
                    f"{show.title} ({show.aired_at.year})" + " {" + show.imdb_id + "}"
                )
                show_path = os.path.join(self.symlink_path, "shows", show_folder)
                if not os.path.exists(show_path):
                    os.mkdir(show_path)
                season = item.parent
                season_folder = f"Season {str(season.number).zfill(2)}"
                season_path = os.path.join(show_path, season_folder)
                if not os.path.exists(season_path):
                    os.mkdir(season_path)
                symlink_path = os.path.join(season_path, symlink_filename)
                update_folder = os.path.join(
                    self.mount_path,
                    os.pardir,
                    "library",
                    "shows",
                    show_folder,
                    season_folder,
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

    def _find_file(self, filename):
        return self.cache.get(filename, None)

    def update_cache(self):
        for root, _, files in os.walk(self.host_path):
            for file in files:
                self.cache[file] = os.path.join(root, file)
