from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from program.media.item import MediaItem
from program.services.content import (
    Listrr,
    Mdblist,
    Overseerr,
    PlexWatchlist,
    TraktContent,
)
from program.services.downloaders import Downloader
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.services.filesystem import FilesystemService
from program.media.state import States
from program.services.indexers import IndexerService
from program.services.post_processing import PostProcessing

# Type aliases for various service types
Scraper = Scraping
Content = Overseerr | PlexWatchlist | Listrr | Mdblist | TraktContent
Service = (
    Content
    | Scraper
    | FilesystemService
    | Updater
    | IndexerService
    | PostProcessing
    | Downloader
)


@dataclass
class ProcessedEvent:
    service: Service | None
    related_media_items: Sequence[MediaItem] | None


@dataclass
class Event:
    emitted_by: Service | Literal["StateTransition", "RetryLibrary"] | str
    item_id: int | None = None
    content_item: "MediaItem | None" = None
    run_at: datetime = datetime.now()
    item_state: States | None = None  # Cached state for priority sorting

    @property
    def log_message(self) -> str:
        """Human-friendly description of the event target for logging."""

        if self.content_item:
            return self.content_item.log_string
        elif self.item_id:
            return f"Item ID {self.item_id}"

        return "Unknown Event"
