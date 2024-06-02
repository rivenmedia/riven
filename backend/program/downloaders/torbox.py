import asyncio
from typing import Generator

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from utils.logger import logger
from utils.request import get


class TorBoxDownloader:
    """TorBox Downloader"""

    def __init__(self, hash_cache):
        self.key = "torbox_downloader"
        self.settings = settings_manager.settings.downloaders.torbox
        self.api_key = self.settings.api_key
        self.base_url = "https://api.torbox.app/v1/api"
        self.headers = {"Authorization": f"{self.api_key}"}
        self.initialized = self.validate()
        if not self.initialized:
            return
        self.hash_cache = hash_cache
        logger.success("TorBox Downloader initialized!")

    def validate(self) -> bool:
        """Validate the TorBox Downloader as a service"""
        return False
        # if not self.settings.enabled:
        #     logger.warning("TorBox Downloader is set to disabled")
        #     return False
        # if not self.api_key:
        #     logger.warning("TorBox Downloader API key is not set")
        #     return False

        # try:
        #     response = get(
        #         f"{self.base_url}/user/me",
        #         additional_headers=self.headers
        #     )
        #     return response.data.is_subscribed
        # except Exception:
        #     return False # for now..

    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Download media item from TorBox"""   
        logger.info(f"Downloading {item.log_string} from TorBox")

    def is_cached(self, infohashes: list[str]) -> list[bool]:
        """Check if the given infohashes are cached in TorBox"""
        cached_results = []
        for infohash in infohashes:
            try:
                response = get(
                    f"{self.base_url}/torrents/checkcached",
                    headers=self.headers,
                    params={"hash": infohash, "format": "object"}
                )
                result = response.json()
                cached = result['data']['data'] if 'data' in result and 'data' in result['data'] and result['data']['data'] is not False else False
                cached_results.append(cached)
            except Exception as e:
                cached_results.append(False)
        return cached_results

    def request_download(self, infohash: str):
        """Request a download from TorBox"""
        try:
            response = get(
                f"{self.base_url}/torrents/requestdl",
                headers=self.headers,
                params={"torrent_id": infohash, "file_id": 0, "zip": False},
            )
            return response.json()
        except Exception as e:
            raise e
    
    async def download_media(self, item: MediaItem):
        """Initiate the download of a media item using TorBox."""
        if not item:
            logger.error("No media item provided for download.")
            return None

        infohash = item.active_stream.get("hash")
        if not infohash:
            logger.error(f"No infohash found for item: {item.log_string}")
            return None

        if self.is_cached([infohash])[0]:
            logger.info(f"Item already cached: {item.log_string}")
        else:
            download_response = self.request_download(infohash)
            if download_response.get('status') != 'success':
                logger.error(f"Failed to initiate download for item: {item.log_string}")
                return None
            logger.info(f"Download initiated for item: {item.log_string}")

        # Wait for the download to be ready and get the path
        download_path = await self.get_torrent_path(infohash)
        if not download_path:
            logger.error(f"Failed to get download path for item: {item.log_string}")
            return None

        logger.success(f"Download ready at path: {download_path} for item: {item.log_string}")
        return download_path

    async def get_torrent_path(self, infohash: str):
        """Check and wait until the torrent is fully downloaded and return the path."""
        for _ in range(30):  # Check for 5 minutes max
            if self.is_cached([infohash])[0]:
                logger.info(f"Torrent cached: {infohash}")
                return self.mount_torrents_path + infohash  # Assuming the path to be mounted torrents path + infohash
            await asyncio.sleep(10)
        logger.warning(f"Torrent not available after timeout: {infohash}")
        return None
