from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

from kink import di
from loguru import logger

from pydantic import BaseModel
from sqlalchemy.orm import Session
from program.db.db import db_session
from program.media.media_entry import MediaEntry
from program.services.streaming.exceptions import (
    DebridServiceLinkUnavailable,
)
from program.media.item import MediaItem
from program.types import Event
from routers.secure.items import apply_item_mutation
from program.utils.debrid_cdn_url import DebridCDNUrl

if TYPE_CHECKING:
    from program.services.downloaders import Downloader


class VFSEntry(TypedDict):
    virtual_path: str
    name: str
    size: int
    is_directory: bool
    entry_type: str | None
    created: str | None
    modified: str | None


class GetEntryByOriginalFilenameResult(BaseModel):
    original_filename: str
    download_url: str | None
    unrestricted_url: str | None
    provider: str | None
    provider_download_id: str | None
    size: int | None
    created: str | None
    modified: str | None
    entry_type: Literal["media", "subtitle"]

    @property
    def url(self) -> str | None:
        """The URL to use for this request."""

        return self.unrestricted_url or self.download_url


class VFSDatabase:
    def __init__(self, downloader: "Downloader | None" = None) -> None:
        """
        Initialize VFS Database.

        Args:
            downloader: Downloader instance with initialized services for URL resolution
        """

        self.downloader = downloader

    # --- Queries ---
    def get_subtitle_content(
        self,
        parent_original_filename: str,
        language: str,
    ) -> bytes | None:
        """
        Get the subtitle content for a SubtitleEntry.

        In the new architecture, subtitles are looked up by their parent video's
        original_filename and language code, not by path.

        Parameters:
            parent_original_filename (str): Original filename of the parent MediaEntry (video file).
            language (str): ISO 639-3 language code (e.g., 'eng').

        Returns:
            bytes: Subtitle content encoded as UTF-8, or None if not found or not a subtitle.
        """

        with db_session() as s:
            from program.media.subtitle_entry import SubtitleEntry

            # Query specifically for SubtitleEntry by parent and language
            subtitle = (
                s.query(SubtitleEntry)
                .filter_by(
                    parent_original_filename=parent_original_filename, language=language
                )
                .first()
            )

            if subtitle and subtitle.content:
                return subtitle.content.encode("utf-8")

            return None

    def refresh_unrestricted_url(
        self,
        entry: MediaEntry,
        session: Session,
    ) -> str | None:
        """
        Refresh the unrestricted URL for a MediaEntry using the downloader services.

        Args:
            entry: MediaEntry to refresh
        """

        if not self.downloader:
            logger.warning("No downloader available to refresh unrestricted URL")

            return None

        from program.program import Program

        # Find service by matching the key attribute (services dict uses class as key)
        service = next(
            (
                svc
                for svc in self.downloader.services.values()
                if svc.key == entry.provider
            ),
            None,
        )

        if service and entry.download_url:
            try:
                new_unrestricted = service.unrestrict_link(entry.download_url)

                if new_unrestricted:
                    DebridCDNUrl(entry).validate(attempt_refresh=False)

                    entry.unrestricted_url = new_unrestricted.download

                    session.merge(entry)
                    session.commit()

                    logger.debug(
                        f"Refreshed unrestricted URL for {entry.original_filename}"
                    )

                    return entry.unrestricted_url
            except DebridServiceLinkUnavailable as e:
                logger.warning(
                    f"Failed to unrestrict URL for {entry.original_filename}: {e}"
                )

                # If un-restricting fails, reset the MediaItem to trigger a new download
                if entry.media_item:
                    item_id = entry.media_item.id

                    def mutation(i: MediaItem, s: Session):
                        i.blacklist_active_stream()
                        i.reset()

                    with db_session() as s:
                        apply_item_mutation(
                            program=di[Program],
                            item=entry.media_item,
                            mutation_fn=mutation,
                            session=s,
                        )

                        s.commit()

                    di[Program].em.add_event(
                        Event(
                            "VFS",
                            item_id,
                        )
                    )

                    return None
                raise
            except Exception as e:
                logger.warning(
                    f"Failed to unrestrict URL for {entry.original_filename}: {e}"
                )

    def get_entry_by_original_filename(
        self,
        original_filename: str,
        force_resolve: bool = False,
    ) -> GetEntryByOriginalFilenameResult | None:
        """
        Get entry metadata and download URL by original filename.

        This is the NEW API that replaces path-based lookups.

        Args:
            original_filename: Original filename from debrid provider
            force_resolve: If True, force refresh of unrestricted URL from provider

        Returns:
            Dictionary with entry metadata and URLs, or None if not found
        """

        try:
            with db_session() as session:
                entry = (
                    session.query(MediaEntry)
                    .filter(MediaEntry.original_filename == original_filename)
                    .first()
                )

                if not entry:
                    return None

                # Get download URL (with optional unrestricting)
                download_url = entry.download_url
                unrestricted_url = entry.unrestricted_url

                # If force_resolve or no unrestricted URL, try to unrestrict
                if (force_resolve or not unrestricted_url) and (
                    self.downloader and entry.provider
                ):
                    unrestricted_url = self.refresh_unrestricted_url(
                        entry,
                        session=session,
                    )

            return GetEntryByOriginalFilenameResult(
                original_filename=entry.original_filename,
                download_url=download_url,
                unrestricted_url=unrestricted_url,
                provider=entry.provider,
                provider_download_id=entry.provider_download_id,
                size=entry.file_size,
                created=(entry.created_at.isoformat()),
                modified=(entry.updated_at.isoformat()),
                entry_type="media",
            )
        except DebridServiceLinkUnavailable:
            raise
        except Exception as e:
            logger.error(
                f"Error getting entry by original_filename {original_filename}: {e}"
            )
            return None
