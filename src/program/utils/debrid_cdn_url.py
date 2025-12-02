import httpx
from loguru import logger

from http import HTTPStatus
from kink import di

from program.services.filesystem.vfs.db import VFSDatabase
from program.settings import settings_manager
from program.services.streaming.media_stream import PROXY_REQUIRED_PROVIDERS


class DebridCDNUrl:
    """DebridCDNUrl class"""

    def __init__(self, filename: str) -> None:
        self.filename = filename

        entry_info = di[VFSDatabase].get_entry_by_original_filename(
            original_filename=self.filename,
        )

        if not entry_info:
            raise ValueError("Could not find entry info for CDN URL validation")

        if not entry_info.url:
            raise ValueError("Could not find URL in entry info for CDN URL validation")

        self.url = entry_info.url
        self.provider = entry_info.provider

    def validate(self) -> str | None:
        """Get a validated CDN URL, refreshing if necessary."""

        try:
            # Assert URL availability by opening a stream
            # Create client with proxy if needed
            client_kwargs = {}
            
            if self.provider in PROXY_REQUIRED_PROVIDERS:
                proxy_url = settings_manager.settings.downloaders.proxy_url
                if proxy_url:
                    client_kwargs["proxy"] = proxy_url

            with httpx.Client(**client_kwargs) as client:
                with client.stream(method="GET", url=self.url) as response:
                    response.raise_for_status()

                    return self.url
        except httpx.ConnectError as e:
            logger.error(f"Connection error while validating CDN URL {self.url}: {e}")

            return None
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code

            if status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE):
                self._refresh()
                logger.debug(f"Refreshed CDN URL for {self.filename}")
                return self.validate()

            raise

    def _refresh(self) -> None:
        """Refresh the CDN URL."""

        entry = di[VFSDatabase].get_entry_by_original_filename(
            original_filename=self.filename,
            force_resolve=True,
        )

        if not entry:
            raise ValueError("Could not refresh CDN URL; entry not found")

        if not (url := entry.url):
            raise ValueError("Could not refresh CDN URL; no URL found in entry")

        self.url = url
