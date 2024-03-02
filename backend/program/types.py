from dataclasses import dataclass
from typing import Union, Generator

from program.content import Overseerr, PlexWatchlist, Listrr, Mdblist
from program.media.item import MediaItem
from program.libaries import SymlinkLibrary
from program.realdebrid import Debrid
from program.scrapers import Scraping, Torrentio, Orionoid, Jackett
from program.symlink import Symlinker

# Typehint classes
Scraper = Union[Scraping, Torrentio, Orionoid, Jackett]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist]
Service = Union[Content, SymlinkLibrary, Scraper, Debrid, Symlinker]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]
ProcessedEvent = (MediaItem, Service, list[MediaItem])

@dataclass
class Event:
    emitted_by: Service
    item: MediaItem
