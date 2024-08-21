from pathlib import Path
from typing import Any, Generator
from RTN import ParsedData, parse
from program.media.item import MediaItem, Movie, Show
from utils.request import get
from loguru import logger
from program.indexers.trakt import CLIENT_ID, TraktIndexer
from program.downloaders.realdebrid import RealDebridDownloader

class RealDebridLibrary:
    """Real-Debrid Library"""
    def __init__(self, rd_cls: RealDebridDownloader, trakt_run: TraktIndexer.run):
        self.rd = rd_cls
        self.index = trakt_run
        self.key = "realdebrid_library"
        self.initialized = rd_cls.settings.match_existing_content and rd_cls.initialized
        self.processed_imdb_ids = []

    def run(self, session) -> Generator[Movie | Show, Any, Any]:
        """Run the Real-Debrid library"""
        torrents = self.get_torrents(1000)
        for torrent in torrents:
            try:
                parsed_data = parse(torrent.name)
                title, imdb_id, year = self.match_torrent_from_trakt(parsed_data)
                if not self.imdb_exists_in_db(session, imdb_id) and imdb_id not in self.processed_imdb_ids:
                    if title and imdb_id and year:
                        logger.debug(f"Matched RD torrent ({torrent.name}) to {title} ({year}) - {imdb_id}")
                        self.processed_imdb_ids.append(imdb_id)
                        item = None
                        if parsed_data.type == "movie":
                            item = next(self.index(Movie({"imdb_id": imdb_id, "requested_by": self.key})))
                        elif parsed_data.type == "show":
                            item = next(self.index(Show({"imdb_id": imdb_id, "requested_by": self.key})))
                        if item:
                            item.active_stream = {"hash": torrent.infohash, "name": torrent.name}
                            info = self.rd.get_torrent_info(torrent.id)
                            files = [file for file in info.files if file.selected]
                            container = {}
                            for file in files:
                                container[file.id] = {"filesize": file.bytes, "filename": Path(file.path).name}
                            if item.type == "movie":
                                self.rd._is_wanted_movie(container, item)
                                yield item
                            elif item.type == "show":
                                self.rd._is_wanted_show(container, item)
                                yield item
            except:
                logger.debug(f"Failed to match torrent: {torrent.id} - {torrent.infohash}")

    def imdb_exists_in_db(self, session, imdb_id: str) -> bool:
        """Check if an IMDB ID exists in the database"""
        with session:
            if session.query(MediaItem).filter(MediaItem.imdb_id == imdb_id).first() is not None:
                logger.debug(f"IMDB ID {imdb_id} found in DB")
                return True
            logger.debug(f"IMDB ID {imdb_id} not found in DB")
            return False

    def get_torrent_info(self, id: str) -> dict:
        """Get torrent info from real-debrid.com"""
        try:
            response = get(
                f"https://api.real-debrid.com/rest/1.0/torrents/info/{id}",
                additional_headers=self.rd.auth_headers,
                proxies=self.rd.proxy,
                specific_rate_limiter=self.rd.torrents_rate_limiter,
                overall_rate_limiter=self.rd.overall_rate_limiter,
                response_type=dict
            )
            if response.is_ok and response.data:
                return response.data
        except Exception as e:
            logger.error(f"Error getting torrent info from Real-Debrid: {e}")
        return {}

    def match_torrent_from_trakt(self, data: ParsedData) -> str | None:
        """Match a torrent to a Trakt item"""
        response_list = self.trakt_search(data.type, data.parsed_title)
        for response in response_list:
            response_data = response.get(data.type, {})
            if response_data and response_data["year"] == data.year:
                return response_data["title"], response_data["ids"]["imdb"], response_data["year"]
        return None, None

    def get_torrents(self, limit: int) -> list["RealDebridTorrent"]:
        """Get torrents from real-debrid.com"""
        try:
            response = get(
                f"https://api.real-debrid.com/rest/1.0/torrents?limit={str(limit)}",
                additional_headers=self.rd.auth_headers,
                proxies=self.rd.proxy,
                specific_rate_limiter=self.rd.torrents_rate_limiter,
                overall_rate_limiter=self.rd.overall_rate_limiter,
                response_type=dict
            )
            if response.is_ok and response.data:
                return [RealDebridTorrent(torrent) for torrent in response.data]
        except Exception as e:
            logger.error(f"Error getting torrents from Real-Debrid: {e}")
        return []

    def trakt_search(self, type, query):
        """Search Trakt for a media item"""
        try:
            response = get(
                f"https://api.trakt.tv/search/{type}?query={query}",
                additional_headers={"trakt-api-version": "2", "trakt-api-key": CLIENT_ID},
                response_type=dict)
            if response.is_ok and response.data:
                return response.data
        except Exception as e:
            logger.error(f"Error searching Trakt: {e}")
        return []

class RealDebridTorrent:
    """Real-Debrid Torrent"""
    def __init__(self, data: dict):
        self.id = data.get("id")
        self.name = data.get("filename")
        self.infohash = data.get("hash")
        self.status = data.get("status")
