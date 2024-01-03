"""Realdebrid module"""
import os
import re
import time
from typing import Optional
from pydantic import BaseModel
from requests import ConnectTimeout
from utils.logger import logger
from utils.request import get, post, ping
from utils.settings import settings_manager
from utils.utils import parser


WANTED_FORMATS = [".mkv", ".mp4", ".avi"]
RD_BASE_URL = "https://api.real-debrid.com/rest/1.0"


class DebridConfig(BaseModel):
    api_key: Optional[str]


class Debrid:
    """Real-Debrid API Wrapper"""

    def __init__(self):
        # Realdebrid class library is a necessity
        self.initialized = False
        while True:
            self.key = "realdebrid"
            self.settings = DebridConfig(**settings_manager.get(self.key))
            self.auth_headers = {"Authorization": f"Bearer {self.settings.api_key}"}
            self.running = False
            if self._validate_settings():
                self._torrents = {}
                break
            logger.error(
                "Realdebrid settings incorrect or not premium, retrying in 2..."
            )
            time.sleep(2)
        self.initialized = True

    def _validate_settings(self):
        try:
            response = ping(
                "https://api.real-debrid.com/rest/1.0/user",
                additional_headers=self.auth_headers,
            )
            if response.ok:
                json = response.json()
                return json["premium"] > 0
        except ConnectTimeout:
            return False

    def run(self, item):
        self.download(item)

    def download(self, item):
        """Download given media items from real-debrid.com"""
        self._download(item)

    def _download(self, item):
        """Download movie from real-debrid.com"""
        downloaded = 0
        self._check_stream_availability(item)
        self._determine_best_stream(item)
        if not self._is_downloaded(item):
            downloaded = self._download_item(item)
        self._update_torrent_info(item)
        self._set_file_paths(item)
        return downloaded

    def _is_downloaded(self, item):
        if not item.get("active_stream", None):
            return False
        torrents = self.get_torrents()
        for torrent in torrents:
            if torrent.hash == item.active_stream.get("hash"):
                item.set("active_stream.id", torrent.id)
                logger.debug("Torrent already downloaded")
                return True
        return False

    def _update_torrent_info(self, item):
        info = self.get_torrent_info(item.get("active_stream")["id"])
        item.active_stream["name"] = info.filename

    def _download_item(self, item):
        request_id = self.add_magnet(item)

        time.sleep(0.3)
        self.select_files(request_id, item)
        item.set("active_stream.id", request_id)

        if item.type == "movie":
            log_string = item.title
        if item.type == "season":
            log_string = f"{item.parent.title} S{item.number}"
        if item.type == "episode":
            log_string = (
                f"{item.parent.parent.title} S{item.parent.number}E{item.number}"
            )

        logger.debug("Downloaded %s", log_string)
        return 1

    def _get_torrent_info(self, request_id):
        data = self.get_torrent_info(request_id)
        if not data["id"] in self._torrents.keys():
            self._torrents[data["id"]] = data

    def _determine_best_stream(self, item) -> bool:
        """Returns true if season stream found for episode"""
        for hash, stream in item.streams.items():
            if stream.get("cached"):
                item.set("active_stream", stream)
                item.set("active_stream.hash", hash)
                break
        match (item.type):
            case "movie":
                log_string = item.title
            case "season":
                log_string = f"{item.parent.title} S{item.number}"
            case "episode":
                log_string = f"{item.parent.parent.title} S{item.parent.number}E{item.number}"
            case _:
                log_string = ""

        if item.get("active_stream", None):
            logger.debug("Found cached release for %s", log_string)
        else:
            logger.debug("No cached release found for %s", log_string)
            item.streams = {}
        return False

    def _check_stream_availability(self, item):
        if len(item.streams) == 0:
            return
        streams = "/".join(list(item.streams))
        response = get(
            f"https://api.real-debrid.com/rest/1.0/torrents/instantAvailability/{streams}/",
            additional_headers=self.auth_headers,
            response_type=dict,
        )
        cached = False
        for stream_hash, provider_list in response.data.items():
            if len(provider_list) == 0:
                continue
            for containers in provider_list.values():
                for container in containers:
                    wanted_files = {
                        file_id: file
                        for file_id, file in container.items()
                        if os.path.splitext(file["filename"])[1] in WANTED_FORMATS
                    }
                    if len(wanted_files) >= 1:
                        cached = False
                        if item.type == "season":
                            episodes = []
                            for file in wanted_files.values():
                                episodes += parser.episodes_in_season(
                                    item.number, file["filename"]
                                )
                            if len(episodes) >= len(item.episodes):
                                cached = True
                        if item.type == "movie":
                            if len(wanted_files) == 1:
                                cached = True
                        if item.type == "episode":
                            for file in wanted_files.values():
                                episodes = parser.episodes_in_season(
                                    item.parent.number, file["filename"]
                                )
                                if item.number in episodes:
                                    cached = True
                                    break
                    item.streams[stream_hash]["files"] = wanted_files
                    item.streams[stream_hash]["cached"] = cached
                    if cached:
                        return

    def _real_episode_count(self, files):
        def count_episodes(episode_numbers):
            count = 0
            for episode in episode_numbers:
                if "-" in episode:
                    start, end = map(int, episode.split("-"))
                    count += end - start + 1
                else:
                    count += 1
            return count

        total_count = 0
        for file in files.values():
            episode_numbers = re.findall(
                r"E(\d{1,2}(?:-\d{1,2})?)",
                file["filename"],
                re.IGNORECASE,
            )
            total_count += count_episodes(episode_numbers)
        return total_count

    def _set_file_paths(self, item):
        if item.type == "movie":
            self._handle_movie_paths(item)
        if item.type == "season":
            self._handle_season_paths(item)
        if item.type == "episode":
            self._handle_episode_paths(item)

    def _handle_movie_paths(self, item):
        item.set("folder", item.active_stream.get("name"))
        item.set(
            "file",
            next(iter(item.active_stream["files"].values())).get("filename"),
        )

    def _handle_season_paths(self, season):
        for file in season.active_stream["files"].values():
            for episode in parser.episodes_in_season(season.number, file["filename"]):
                if episode - 1 in range(len(season.episodes)):
                    season.episodes[episode - 1].set(
                        "folder", season.active_stream.get("name")
                    )
                    season.episodes[episode - 1].set("file", file["filename"])

    def _handle_episode_paths(self, episode):
        for file in episode.active_stream["files"].values():
            for episode_number in parser.episodes(file["filename"]):
                if episode.number == episode_number:
                    episode.set("folder", episode.active_stream.get("name"))
                    episode.set("file", file["filename"])

    def add_magnet(self, item) -> str:
        """Add magnet link to real-debrid.com"""
        if not item.active_stream.get("hash"):
            return None
        response = post(
            "https://api.real-debrid.com/rest/1.0/torrents/addMagnet",
            {
                "magnet": "magnet:?xt=urn:btih:"
                + item.active_stream["hash"]
                + "&dn=&tr="
            },
            additional_headers=self.auth_headers,
        )
        if response.is_ok:
            return response.data.id
        return None

    def get_torrents(self) -> str:
        """Add magnet link to real-debrid.com"""
        response = get(
            "https://api.real-debrid.com/rest/1.0/torrents/",
            data={"offset": 0, "limit": 2500},
            additional_headers=self.auth_headers,
        )
        if response.is_ok:
            return response.data
        return None

    def select_files(self, request_id, item) -> bool:
        """Select files from real-debrid.com"""
        files = item.active_stream.get("files")
        response = post(
            f"https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{request_id}",
            {"files": ",".join(files.keys())},
            additional_headers=self.auth_headers,
        )
        return response.is_ok

    def get_torrent_info(self, request_id):
        """Get torrent info from real-debrid.com"""
        response = get(
            f"https://api.real-debrid.com/rest/1.0/torrents/info/{request_id}",
            additional_headers=self.auth_headers,
        )
        if response.is_ok:
            return response.data
