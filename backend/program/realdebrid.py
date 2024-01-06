"""Realdebrid module"""
import os
from pathlib import Path
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

    def __init__(self, _):
        # Realdebrid class library is a necessity
        self.initialized = False
        self.key = "real_debrid"
        self.settings = DebridConfig(**settings_manager.get(self.key))
        self.auth_headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        self.running = False
        if not self._validate_settings():
            logger.error("Realdebrid settings incorrect or not premium!")
            return
        logger.info("Real Debrid initialized!")
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
        if self.is_cached(item):
            if not self._is_downloaded(item):
                downloaded = self._download_item(item)
            self._set_file_paths(item)
            return downloaded

    def _is_downloaded(self, item):
        torrents = self.get_torrents()
        for torrent in torrents:
            if torrent.hash == item.active_stream.get("hash"):
                item.set("active_stream.id", torrent.id)
                self.set_active_files(item)
                logger.debug("Torrent for %s already downloaded", item.log_string)
                return True
        return False

    def _download_item(self, item):
        request_id = self.add_magnet(item)
        item.set("active_stream.id", request_id)
        self.set_active_files(item)
        self.select_files(request_id, item)
        item.set("active_stream.id", request_id)
        logger.debug("Downloaded %s", item.log_string)
        return 1

    def _get_torrent_info(self, request_id):
        data = self.get_torrent_info(request_id)
        if not data["id"] in self._torrents.keys():
            self._torrents[data["id"]] = data

    def set_active_files(self, item):
        info = self.get_torrent_info(item.get("active_stream")["id"])
        item.active_stream["name"] = info.filename

        for file in info.files:
            extension = os.path.splitext(file.path)[1]
            if extension in WANTED_FORMATS:
                filename = os.path.basename(file.path)
                item.active_stream["files"][str(file.id)] = {"filename": filename}

    def is_cached(self, item):
        if len(item.streams) == 0:
            return

        def chunks(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i : i + n]

        stream_chunks = list(chunks(list(item.streams), 5))

        for stream_chunk in stream_chunks:
            streams = "/".join(stream_chunk)
            response = get(
                f"https://api.real-debrid.com/rest/1.0/torrents/instantAvailability/{streams}/",
                additional_headers=self.auth_headers,
                response_type=dict,
            )
            for stream_hash, provider_list in response.data.items():
                if len(provider_list) == 0:
                    continue
                for containers in provider_list.values():
                    for container in containers:
                        for file in container.values():
                            if Path(file["filename"]).suffix in WANTED_FORMATS:
                                item.set(
                                    "active_stream",
                                    {"hash": stream_hash, "files": {}, "id": None},
                                )
                                return True
        return False

    def _set_file_paths(self, item):
        if item.type == "movie":
            self._handle_movie_paths(item)
        if item.type == "season":
            self._handle_season_paths(item)
        if item.type == "episode":
            self._handle_episode_paths(item)

    def _handle_movie_paths(self, item):
        def is_wanted(file: str, item):
            if Path(file).stem == item.active_stream["name"]:
                item.set("file", file)
                return True

        item.set("folder", item.active_stream.get("name"))
        for file in item.active_stream["files"].values():
            if type(file) == dict:
                for sub_file in file.values():
                    if is_wanted(sub_file, item):
                        return
            else:
                if is_wanted(file, item):
                    return

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
                    return

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
