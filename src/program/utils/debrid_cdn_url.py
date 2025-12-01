import httpx
from loguru import logger

from http import HTTPStatus
from kink import di

from program.services.filesystem.vfs.db import VFSDatabase


class DebridCDNUrl:
    """DebridCDNUrl class"""

    def __init__(self, filename: str) -> None:
        self.filename = filename

        entry_info = di[VFSDatabase].get_entry_by_original_filename(
            original_filename=self.filename,
        )

        if not entry_info:
            raise ValueError("Could not find entry info for CDN URL validation")

        if not entry_info["url"]:
            raise ValueError("Could not find URL in entry info for CDN URL validation")

        self.url = entry_info["url"]

    def validate(self) -> str:
        """Get a validated CDN URL, refreshing if necessary."""

        try:
            # Assert URL availability by opening a stream
            with httpx.stream(method="GET", url=self.url) as response:
                response.raise_for_status()

                return self.url
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code

            if status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE):
                refreshed_url = self._refresh()

                if refreshed_url:
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

        url = entry["url"]

        if not url:
            raise ValueError("Could not refresh CDN URL; no URL found in entry")

        self.url = url
