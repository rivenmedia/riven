"""Realdebrid module"""
import os
import re
import threading
import time
import requests
import PTN
from requests import ConnectTimeout
from utils.logger import logger
from utils.request import get, post, ping
from utils.settings import settings_manager
from program.media import MediaItem, MediaItemContainer, MediaItemState


WANTED_FORMATS = [".mkv", ".mp4", ".avi"]
RD_BASE_URL = "https://api.real-debrid.com/rest/1.0"


def get_user():
    api_key = settings_manager.get("realdebrid")["api_key"]
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(
        "https://api.real-debrid.com/rest/1.0/user", headers=headers
    )
    return response.json()


class Debrid(threading.Thread):
    """Real-Debrid API Wrapper"""

    def __init__(self, media_items: MediaItemContainer):
        super().__init__(name="Debrid")
        # Realdebrid class library is a necessity
        while True:
            self.settings = settings_manager.get("realdebrid")
            self.media_items = media_items
            self.auth_headers = {"Authorization": f'Bearer {self.settings["api_key"]}'}
            self.running = False
            if self._validate_settings():
                self._torrents = {}
                break
            logger.error(
                "Realdebrid settings incorrect or not premium, retrying in 2..."
            )
            time.sleep(2)

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

    def run(self):
        while self.running:
            self.download()

    def start(self) -> None:
        self.running = True
        super().start()

    def stop(self) -> None:
        self.running = False
        super().join()

    def download(self):
        """Download given media items from real-debrid.com"""
        added_files = 0

        items = []
        for item in self.media_items:
            if item.state is not MediaItemState.LIBRARY:
                if item.type == "movie" and item.state is MediaItemState.SCRAPE:
                    items.append(item)
                if item.type == "show":
                    item._lock.acquire()
                    for season in item.seasons:
                        if season.state is MediaItemState.SCRAPE:
                            items.append(season)
                        else:
                            for episode in season.episodes:
                                if episode.state is MediaItemState.SCRAPE:
                                    items.append(episode)
                    item._lock.release()

        for item in items:
            added_files += self._download(item)

        if added_files > 0:
            logger.info("Downloaded %s cached releases", added_files)

    def _download(self, item):
        """Download movie from real-debrid.com"""
        downloaded = 0
        self._check_stream_availability(item)
        self._determine_best_stream(item)
        if not self._is_downloaded(item):
            downloaded = self._download_item(item)
        self._update_torrent_info(item)
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
            log_string = f"{item.parent.parent.title} S{item.parent.number}E{item.number}"

        logger.debug("Downloaded %s", log_string)
        return 1

    def _get_torrent_info(self, request_id):
        data = self.get_torrent_info(request_id)
        if not data["id"] in self._torrents.keys():
            self._torrents[data["id"]] = data

    def _determine_best_stream(self, item) -> bool:
        """Returns true if season stream found for episode"""
        cached = [
            stream_hash
            for stream_hash, stream_value in item.streams.items()
            if stream_value.get("cached")
        ]
        for stream_hash, stream in item.streams.items():
            if item.type == "episode":
                if stream.get("files") and self._real_episode_count(
                    stream["files"]
                ) >= len(item.parent.episodes):
                    item.parent.set("active_stream", stream)
                    logger.debug(
                        "Found cached release for %s %s",
                        item.parent.parent.title,
                        item.parent.number,
                    )
                    return True
                if (
                    stream.get("files")
                    and self._real_episode_count(stream["files"]) == 0
                ):
                    continue
            if stream_hash in cached:
                stream["hash"] = stream_hash
                item.set("active_stream", stream)
                break
        match (item.type):
            case "movie":
                log_string = item.title
            case "season":
                log_string = f"{item.parent.title} season {item.number}"
            case "episode":
                log_string = f"{item.parent.parent.title} season {item.parent.number} episode {item.number}"
            case _:
                log_string = ""

        if item.get("active_stream", None):
            logger.debug("Found cached release for %s", log_string)
        else:
            logger.debug("No cached release found for %s", log_string)
            item.streams = {}
        return False

    def _check_stream_availability(self, item: MediaItem):
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
                    wanted_files = None
                    if item.type in ["movie", "season"]:
                        wanted_files = {
                            file_id: file
                            for file_id, file in container.items()
                            if os.path.splitext(file["filename"])[1] in WANTED_FORMATS
                            and file["filesize"] > 50000000
                        }
                    if item.type == "episode":
                        for file_id, file in container.items():
                            parse = PTN.parse(file["filename"])
                            episode = parse.get("episode")
                            if type(episode) == list:
                                if item.number in episode:
                                    wanted_files = {file_id: file}
                                    break
                            elif item.number == episode:
                                wanted_files = {file_id: file}
                                break
                    if wanted_files:
                        cached = False
                        if item.type == "season":
                            if self._real_episode_count(wanted_files) >= len(
                                item.episodes
                            ):
                                cached = True
                        if item.type == "movie":
                            if len(wanted_files) == 1:
                                cached = True
                        if item.type == "episode":
                            if len(wanted_files) >= 1:
                                cached = True
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

    def add_magnet(self, item: MediaItem) -> str:
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
