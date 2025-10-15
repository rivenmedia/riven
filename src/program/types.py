from dataclasses import dataclass
from datetime import datetime
from typing import Generator, Optional, Union

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
    TorBoxDownloader,
)
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.services.filesystem import FilesystemService

# Typehint classes
Scraper = Union[Scraping]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist, TraktContent]
Downloader = Union[
    RealDebridDownloader,
    TorBoxDownloader,
]

Service = Union[Content, Scraper, Downloader, FilesystemService, Updater]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]


class ProcessedEvent:
    service: Service
    related_media_items: list[MediaItem]


@dataclass
class Event:
    emitted_by: Service
    item_id: Optional[str] = None
    content_item: Optional[MediaItem] = None
    run_at: datetime = datetime.now()
    item_state: Optional[str] = None  # Cached state for priority sorting

    @property
    def log_message(self):
        # Defensive: content_item may be None
        external_id = None
        if self.content_item:
            if self.content_item.tmdb_id:
                external_id = f"TMDB ID {self.content_item.tmdb_id}"
            elif self.content_item.tvdb_id:
                external_id = f"TVDB ID {self.content_item.tvdb_id}"
            elif self.content_item.imdb_id:
                external_id = f"IMDB ID {self.content_item.imdb_id}"
        elif self.item_id:
            return f"Item ID {self.item_id}"
        elif external_id:
            return f"External ID {external_id}"
        else:
            return "Unknown Event"
