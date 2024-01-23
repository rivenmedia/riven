"""Iceberg settings models"""

from typing import Optional
from pydantic import BaseModel


class PlexModel(BaseModel):
    user: Optional[str] = ""
    token: str = ""
    url: str = "http://localhost:32400"

class DebridModel(BaseModel):
    api_key: str = ""

class SymlinkModel(BaseModel):
    host_path: str = ""
    container_path: str = ""

# Content Services

class ListrrModel(BaseModel):
    enabled: bool = False
    movie_lists: Optional[list[str]] = [""]
    show_lists: Optional[list[str]] = [""]
    api_key: Optional[str] = ""
    update_interval: int = 80

class MdblistModel(BaseModel):
    enabled: bool = False
    api_key: Optional[str] = ""
    lists: Optional[list[str]] = [""]

class OverseerrModel(BaseModel):
    enabled: bool = False
    url: Optional[str] = "http://localhost:5055"
    api_key: Optional[str] = ""

class PlexWatchlistModel(BaseModel):
    enabled: bool = False
    rss: Optional[str] = ""

class ContentModel(BaseModel):
    listrr: ListrrModel = ListrrModel()
    mdblist: MdblistModel = MdblistModel()
    overseerr: OverseerrModel = OverseerrModel()
    plex_watchlist: PlexWatchlistModel = PlexWatchlistModel()

# Scraper Services

class JackettConfig(BaseModel):
    enabled: bool = False
    url: Optional[str] = "http://localhost:9117"

class OrionoidConfig(BaseModel):
    enabled: bool = False
    api_key: Optional[str] = ""

class TorrentioConfig(BaseModel):
    enabled: bool = False
    filter: Optional[str] = "sort=qualitysize%7Cqualityfilter=480p,scr,cam,unknown"

class ScraperModel(BaseModel):
    after_2: int = 0.5,
    after_5: int = 2,
    after_10: int = 24,
    jackett: JackettConfig = JackettConfig()
    orionoid: OrionoidConfig = OrionoidConfig()
    torrentio: TorrentioConfig = TorrentioConfig()


class AppModel(BaseModel):
    version: str = "0.4.3"
    debug: bool = True
    log: bool = True
    plex: PlexModel = PlexModel()
    real_debrid: DebridModel = DebridModel()
    symlink: SymlinkModel = SymlinkModel()
    content: ContentModel = ContentModel()
    scraper: ScraperModel = ScraperModel()
