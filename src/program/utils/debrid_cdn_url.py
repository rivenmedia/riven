from typing import Self
import httpx
from loguru import logger

from http import HTTPStatus
from kink import di

from program.settings import settings_manager
from program.services.streaming.media_stream import PROXY_REQUIRED_PROVIDERS
from program.services.streaming.exceptions import (
    DebridServiceLinkUnavailable,
)
from program.media.media_entry import MediaEntry
from program.db.db import db_session


class DebridCDNUrl:
    """DebridCDNUrl class"""

    def __init__(self, entry: MediaEntry) -> None:
        self.filename = entry.original_filename
        self.entry = entry

        if not entry.url:
            raise ValueError("Could not find URL in entry info for CDN URL validation")

        self.url = entry.url
        self.provider = entry.provider

    @classmethod
    def from_filename(cls, filename: str) -> Self:
        """Create DebridCDNUrl from filename."""

        with db_session() as s:
            entry = (
                s.query(MediaEntry)
                .filter(MediaEntry.original_filename == filename)
                .first()
            )

        if not entry:
            raise ValueError("Could not find entry info for CDN URL validation")

        return cls(entry)

    def validate(
        self,
        attempt_refresh: bool = True,
        attempt: int = 1,
    ) -> str | None:
        """Get a validated CDN URL, refreshing if necessary."""

        try:
            # Assert URL availability by opening a stream, using a proxy if needed
            proxy = (
                self.provider in PROXY_REQUIRED_PROVIDERS
                and settings_manager.settings.downloaders.proxy_url
                or None
            )

            with httpx.Client(proxy=proxy) as client:
                with client.stream(method="GET", url=self.url) as response:
                    response.raise_for_status()

                    return self.url
        except httpx.TimeoutException as e:
            logger.error(f"Timeout while validating CDN URL {self.url}: {e}")
        except httpx.ConnectError as e:
            logger.error(f"Connection error while validating CDN URL {self.url}: {e}")
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code

            if status_code in (HTTPStatus.NOT_FOUND, HTTPStatus.GONE) and attempt <= 3:
                if attempt_refresh and self._refresh():
                    return self.validate(attempt=attempt + 1)
                else:
                    # If the URL hasn't changed after refreshing, it is likely dead.
                    # Raise an exception to indicate the link is unavailable to trigger a re-scrape.
                    raise DebridServiceLinkUnavailable(
                        provider=self.provider or "Unknown provider",
                        link=self.url,
                    )
        except Exception as e:
            logger.error(f"Unexpected error while validating CDN URL {self.url}: {e}")

        return None

    def _refresh(self) -> bool:
        """Refresh the CDN URL."""

        from program.services.filesystem.vfs.db import VFSDatabase

        url = di[VFSDatabase].refresh_unrestricted_url(self.entry)

        if not url:
            logger.error("Could not refresh CDN URL; no URL returned from refresh")

            return False

        if url == self.url:
            return False

        self.url = url

        logger.debug(f"Refreshed CDN URL for {self.filename}")

        return True
