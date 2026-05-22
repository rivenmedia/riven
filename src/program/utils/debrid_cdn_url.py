from typing import Self
import time
import httpx
from loguru import logger
from urllib.parse import urlparse

from http import HTTPStatus
from kink import di

from program.settings import settings_manager
from program.services.rate_limit import (
    parse_retry_after,
    report_provider_stream_rate_limited,
)
from program.services.streaming.media_stream import PROXY_REQUIRED_PROVIDERS
from program.services.streaming.exceptions import (
    DebridServiceLinkUnavailable,
)
from program.media.media_entry import MediaEntry
from program.db.db import db_session


class RefreshedURLIdenticalException(Exception):
    """Exception raised when a refreshed URL is identical to the previous URL."""

    pass


def _url_log_hint(url: str | None) -> str:
    """Short, log-safe description of a URL (host + path; query shown as length only)."""
    if not url:
        return "(empty)"
    try:
        p = urlparse(url)
        path = p.path or ""
        if len(path) > 72:
            path = path[:72] + "..."
        q = f"?…({len(p.query)} chars)" if p.query else ""
        return f"{p.scheme}://{p.netloc}{path}{q}"
    except Exception:
        tail = 96
        return url[:tail] + ("…" if len(url) > tail else "")


# Sync validation runs in the FUSE thread; must not block indefinitely on slow CDNs.
_VALIDATE_TIMEOUT = httpx.Timeout(45.0, connect=15.0)


class DebridCDNUrl:
    """DebridCDNUrl class"""

    def __init__(self, entry: MediaEntry) -> None:
        self.filename = entry.original_filename
        self.entry = entry

        self.max_validation_attempts = 3
        self.url = entry.unrestricted_url
        self.provider = entry.provider or "Unknown provider"

    @classmethod
    def from_filename(cls, filename: str) -> Self:
        """Create DebridCDNUrl from filename."""

        with db_session() as session:
            entry = (
                session.query(MediaEntry)
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
        """Get a validated CDN URL, refreshing if requested."""

        try:
            # Assert URL availability by opening a stream, using a proxy if needed
            proxy = (
                self.provider in PROXY_REQUIRED_PROVIDERS
                and settings_manager.settings.downloaders.proxy_url
                or None
            )

            try:
                # If no URL is set, attempt to refresh it first if requested,
                # otherwise return as an invalid URL
                if not self.url:
                    if attempt_refresh:
                        if url := self._refresh():
                            self.url = url
                        else:
                            return None
                    else:
                        return None

                t0 = time.monotonic()
                hint = _url_log_hint(self.url)
                logger.debug(
                    f"CDN validate GET provider={self.provider} attempt={attempt} url={hint}"
                )

                with httpx.Client(proxy=proxy, timeout=_VALIDATE_TIMEOUT) as client:
                    with client.stream(
                        method="GET",
                        url=self.url,
                        follow_redirects=True,
                    ) as response:
                        response.raise_for_status()
                        # Read one chunk so redirect/CDN pipelines complete; some stacks
                        # stall until the first read.
                        for _ in response.iter_bytes(chunk_size=65536):
                            break

                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.debug(
                    f"CDN validate ok provider={self.provider} attempt={attempt} "
                    f"ms={elapsed_ms} url={hint}"
                )

                return self.url
            except httpx.TimeoutException as e:
                logger.error(f"Timeout while validating CDN URL {self.url}: {e}")
            except httpx.ConnectError as e:
                logger.error(
                    f"Connection error while validating CDN URL {self.url}: {e}"
                )
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                if status_code == HTTPStatus.TOO_MANY_REQUESTS:
                    if attempt >= self.max_validation_attempts:
                        report_provider_stream_rate_limited(
                            self.provider,
                            retry_after=parse_retry_after(e.response),
                        )
                elif (
                    status_code
                    in (
                        HTTPStatus.NOT_FOUND,
                        HTTPStatus.GONE,
                        HTTPStatus.BAD_REQUEST,
                    )
                    and attempt == 1
                ):
                    # Only attempt to refresh the URL on the first failure
                    if attempt_refresh:
                        if url := self._refresh():
                            self.url = url
                    else:
                        return None
            except RefreshedURLIdenticalException:
                raise
            except Exception as e:
                logger.error(
                    f"Unexpected error while validating CDN URL {self.url}: {e}"
                )

                return None

            if attempt <= self.max_validation_attempts:
                return self.validate(
                    attempt_refresh=attempt_refresh,
                    attempt=attempt + 1,
                )

            return None
        except RefreshedURLIdenticalException as e:
            # If the URL hasn't changed after refreshing, it is likely dead.
            # Raise an exception to indicate the link is unavailable to trigger a re-scrape.
            raise DebridServiceLinkUnavailable(
                provider=self.provider,
                link=self.url or "Unknown URL",
            ) from e

    def _refresh(self) -> str | None:
        """Refresh the CDN URL."""

        from program.services.filesystem.vfs.db import VFSDatabase

        with db_session() as session:
            entry = session.merge(self.entry)

            url = di[VFSDatabase].refresh_unrestricted_url(
                entry=entry,
                session=session,
            )

            if not url:
                logger.debug(
                    "Could not refresh CDN URL for "
                    f"{self.filename}; refresh returned no URL"
                )

                return None

            if url == self.url:
                raise RefreshedURLIdenticalException()

            self.url = url

            return self.url
