"""Symlinking module"""
import os
import time
import PTN
from utils.settings import settings_manager as settings
from utils.logger import logger
from program.media import MediaItemState
from utils.thread import ThreadRunner


class Symlinker:
    """Content class for mdblist"""

    def __init__(
        self,
    ):
        # Symlinking is required
        while True:
            self.cache = {}
            self.settings = settings.get("symlink")
            self.mount_path = os.path.abspath(self.settings["mount"])
            self.host_path = os.path.abspath(self.settings["host_mount"])
            if os.path.exists(self.host_path):
                self.symlink_path = os.path.join(self.host_path, os.pardir, "library")
                if not os.path.exists(self.symlink_path):
                    os.mkdir(self.symlink_path)
                if not os.path.exists(os.path.join(self.symlink_path, "movies")):
                    os.mkdir(os.path.join(self.symlink_path, "movies"))
                if not os.path.exists(os.path.join(self.symlink_path, "shows")):
                    os.mkdir(os.path.join(self.symlink_path, "shows"))
                self.cache_thread = ThreadRunner(self.update_cache, 10)
                self.cache_thread.start()
                break
            logger.error("Rclone mount not found, retrying in 2...")
            time.sleep(2)

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

    def run(self, media_items):
        logger.debug("Symlinking...")
        items = []
        for item in media_items:
            if item.type == "movie" and item.state is MediaItemState.DOWNLOAD:
                item.file = next(iter(item.active_stream["files"].values())).get(
                    "filename"
                )
                file = self._find_file(item.file)
                if file:
                    item.folder = os.path.dirname(file).split("/")[-1]
                    items.append(item)
            if item.type == "show" and item.state in [
                MediaItemState.LIBRARY_PARTIAL,
                MediaItemState.SYMLINK,
                MediaItemState.DOWNLOAD,
            ]:
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
                                        season.episodes[sub_episode - 1].file = file[
                                            "filename"
                                        ]
                                else:
                                    index = obj["episode"] - 1
                                    if index in range(len(season.episodes)):
                                        season.episodes[obj["episode"] - 1].file = file[
                                            "filename"
                                        ]
                        for episode in season.episodes:
                            if episode.state is MediaItemState.DOWNLOAD:
                                file = self._find_file(episode.file)
                                if file:
                                    episode.folder = os.path.dirname(file).split("/")[
                                        -1
                                    ]
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

            if symlink_path:
                try:
                    os.remove(symlink_path)
                except FileNotFoundError:
                    pass
                os.symlink(
                    os.path.join(self.mount_path, "torrents", item.folder, item.file),
                    symlink_path,
                )
                logger.debug("Created symlink for %s", item.__repr__)
                item.symlinked = True
        logger.debug("Done!")

    def _find_file(self, filename):
        return self.cache.get(filename, None)

    def update_cache(self):
        for root, _, files in os.walk(os.path.join(self.host_path, "torrents")):
            for file in files:
                self.cache[file] = os.path.join(root, file)
