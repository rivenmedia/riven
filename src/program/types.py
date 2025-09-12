from typing import Generator, Union

from program.media.item import MediaItem
from program.services.content import (
    Listrr,
    Mdblist,
    Overseerr,
    PlexWatchlist,
    TraktContent,
)
from program.services.downloaders import (
    AllDebridDownloader,
    RealDebridDownloader,
    TorBoxDownloader,
)
from program.services.libraries import SymlinkLibrary
from program.services.scrapers import (
    Comet,
    Jackett,
    Mediafusion,
    Orionoid,
    Scraping,
    Torrentio,
    Zilean,
)
from program.services.updaters import Updater
from program.symlink import Symlinker

# Typehint classes
Scraper = Union[Scraping, Torrentio, Mediafusion, Orionoid, Jackett, Zilean, Comet]
Content = Union[Overseerr, PlexWatchlist, Listrr, Mdblist, TraktContent]
Downloader = Union[
    RealDebridDownloader,
    AllDebridDownloader,
    TorBoxDownloader,
]

Service = Union[Content, SymlinkLibrary, Scraper, Downloader, Symlinker, Updater]
MediaItemGenerator = Generator[MediaItem, None, MediaItem | None]
