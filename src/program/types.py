from dataclasses import dataclass
from typing import Generator, Tuple, Union

from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist, TraktContent
from program.downloaders import RealDebridDownloader, TorBoxDownloader, AllDebridDownloader
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
from program.updaters import Updater, OverseerrUpdater

# Typehint classes
Scraper = Union[Scraping, Torrentio, Knightcrawler, Mediafusion, Orionoid, Jackett, Annatar, TorBoxScraper, Zilean]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist, TraktContent]
Downloader = Union[RealDebridDownloader, TorBoxDownloader, AllDebridDownloader]
Service = Union[Content, SymlinkLibrary, Scraper, Downloader, Symlinker, Updater, OverseerrUpdater]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]
ProcessedEvent = Tuple[MediaItem, Service, list[MediaItem]]


@dataclass
class Event:
    emitted_by: Service
    item: MediaItem