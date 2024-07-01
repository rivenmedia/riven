from dataclasses import dataclass
from typing import Generator, Union

from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist, TraktContent
from program.downloaders import Debrid, TorBoxDownloader
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
    Zilean,
)
from program.scrapers.torbox import TorBoxScraper
from program.symlink import Symlinker
from program.updaters import Updater

# Typehint classes
Scraper = Union[Scraping, Torrentio, Knightcrawler, Mediafusion, Orionoid, Jackett, Annatar, TorBoxScraper, Zilean]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist, TraktContent]
Downloader = Union[Debrid, TorBoxDownloader]
Service = Union[Content, SymlinkLibrary, Scraper, Downloader, Symlinker, Updater]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]
ProcessedEvent = (MediaItem, Service, list[MediaItem])


@dataclass
class Event:
    emitted_by: Service
    item: MediaItem
