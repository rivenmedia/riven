from dataclasses import dataclass
from typing import Generator, Union

from program.downloaders.realdebrid import Debrid
from program.downloaders.torbox import TorBoxDownloader
from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist, TraktContent
from program.libraries import SymlinkLibrary
from program.media.item import MediaItem
from program.scrapers import (
    Annatar,
    Jackett,
    Knightcrawler,
    Mediafusion,
    Orionoid,
    Scraping,
    Torrentio,
)
from program.scrapers.torbox import TorBoxScraper
from program.symlink import Symlinker

# Typehint classes
Scraper = Union[Scraping, Torrentio, Knightcrawler, Mediafusion, Orionoid, Jackett, Annatar, TorBoxScraper]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist, TraktContent]
Downloader = Union[Debrid, TorBoxDownloader]
Service = Union[Content, SymlinkLibrary, Scraper, Downloader, Symlinker]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]
ProcessedEvent = (MediaItem, Service, list[MediaItem])


@dataclass
class Event:
    emitted_by: Service
    item: MediaItem
