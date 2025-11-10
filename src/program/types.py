from dataclasses import dataclass
from datetime import datetime
from typing import Generator, Literal, Optional, Union

from program.media.item import MediaItem
from program.services.content import (
    Listrr,
    Mdblist,
    Overseerr,
    PlexWatchlist,
    TraktContent,
)
from program.services.downloaders import (
    RealDebridDownloader,
)
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.services.filesystem import FilesystemService

# Typehint classes
Scraper = Union[Scraping]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist, TraktContent]
Downloader = Union[RealDebridDownloader,]

Service = Union[Content, Scraper, Downloader, FilesystemService, Updater]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]


class ProcessedEvent:
    service: Service
    related_media_items: list[MediaItem]


@dataclass
class Event:
    emitted_by: Service | Literal["StateTransition", "RetryLibrary"]
    item_id: int | None = None
    content_item: MediaItem | None = None
    run_at: datetime = datetime.now()
    item_state: str | None = None  # Cached state for priority sorting

    @property
    def log_message(self) -> str:
        """Human-friendly description of the event target for logging."""
        if self.content_item:
            return self.content_item.log_string
        elif self.item_id:
            return f"Item ID {self.item_id}"
        return "Unknown Event"
