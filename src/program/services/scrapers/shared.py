"""Shared functions for scrapers."""
from typing import Dict, Optional, Set, Type

from loguru import logger
from RTN import RTN, ParsedData, Torrent, sort_torrents

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.stream import Stream
from program.settings.manager import settings_manager
from program.settings.versions import models
from program.utils.request import (
    BaseRequestHandler,
    HttpMethod,
    ResponseObject,
    ResponseType,
    Session,
)


scraping_settings = settings_manager.settings.scraping
ranking_settings = settings_manager.settings.ranking
ranking_model = models.get(ranking_settings.profile)
rtn = RTN(ranking_settings, ranking_model)


class ScraperRequestHandler(BaseRequestHandler):
    def __init__(self, session: Session, response_type=ResponseType.SIMPLE_NAMESPACE, custom_exception: Optional[Type[Exception]] = None, request_logging: bool = False):
        super().__init__(session, response_type=response_type, custom_exception=custom_exception, request_logging=request_logging)

    def execute(self, method: HttpMethod, endpoint: str, overriden_response_type: ResponseType = None, **kwargs) -> ResponseObject:
        return super()._request(method, endpoint, overriden_response_type=overriden_response_type, **kwargs)


def _parse_results(item: MediaItem, results: Dict[str, str], log_msg: bool = True) -> Dict[str, Stream]:
    """Parse the results from the scrapers into Torrent objects."""
    torrents: Set[Torrent] = set()
    processed_infohashes: Set[str] = set()
    correct_title: str = item.get_top_title()

    aliases: Dict[str, list[str]] = item.get_aliases() if scraping_settings.enable_aliases else {}
    # we should remove keys from aliases if we are excluding the language
    aliases = {k: v for k, v in aliases.items() if k not in ranking_settings.languages.exclude}

    logger.log("SCRAPER", f"Processing {len(results)} results for {item.log_string}")

    for infohash, raw_title in results.items():
        if infohash in processed_infohashes:
            continue

        try:
            torrent: Torrent = rtn.rank(
                raw_title=raw_title,
                infohash=infohash,
                correct_title=correct_title,
                remove_trash=settings_manager.settings.ranking.options["remove_all_trash"],
                aliases=aliases
            )

            if torrent.data.country and not item.is_anime:
                if _get_item_country(item) != torrent.data.country:
                    if scraping_settings.parse_debug:
                        logger.debug(f"Skipping torrent for incorrect country with {item.log_string}: {raw_title}")
                    continue

            if torrent.data.year and not _check_item_year(item, torrent.data):
                if scraping_settings.parse_debug:
                    logger.debug(f"Skipping torrent for incorrect year with {item.log_string}: {raw_title}")
                continue

            if item.is_anime and scraping_settings.dubbed_anime_only:
                if not torrent.data.dubbed:
                    if scraping_settings.parse_debug:
                        logger.debug(f"Skipping non-dubbed anime torrent for {item.log_string}: {raw_title}")
                    continue

            if item.type == "show":
                # if there are episodes, then check to make sure there are at least 12 or more
                if torrent.data.episodes and len(torrent.data.episodes) >= 12:
                    if scraping_settings.parse_debug:
                        logger.debug(f"Skipping show torrent with too few episodes for {item.log_string}: {raw_title}")
                    continue

            torrents.add(torrent)
            processed_infohashes.add(infohash)
        except Exception as e:
            if scraping_settings.parse_debug and log_msg:
                logger.debug(f"GarbageTorrent: '{raw_title}' - {e}")
            processed_infohashes.add(infohash)
            continue

    if torrents:
        logger.log("SCRAPER", f"Found {len(torrents)} streams for {item.log_string}")
        torrents = sort_torrents(torrents, bucket_limit=scraping_settings.bucket_limit)
        torrents_dict = {}
        for torrent in torrents.values():
            torrents_dict[torrent.infohash.lower()] = Stream(torrent)
        logger.log("SCRAPER", f"Kept {len(torrents_dict)} streams for {item.log_string} after processing bucket limit")
        return torrents_dict

    return {}


# helper functions

def _check_item_year(item: MediaItem, data: ParsedData) -> bool:
    """Check if the year of the torrent is within the range of the item."""
    return data.year in [item.aired_at.year - 1, item.aired_at.year, item.aired_at.year + 1]

def _get_item_country(item: MediaItem) -> str:
    """Get the country code for a country."""
    if item.type == "season":
        return item.parent.country.upper()
    elif item.type == "episode":
        return item.parent.parent.country.upper()
    return item.country.upper()

def _get_stremio_identifier(item: MediaItem) -> tuple[str | None, str, str]:
    """Get the stremio identifier for a media item based on its type."""
    if isinstance(item, Show):
        identifier, scrape_type, imdb_id = ":1:1", "series", item.imdb_id
    elif isinstance(item, Season):
        identifier, scrape_type, imdb_id = f":{item.number}:1", "series", item.parent.imdb_id
    elif isinstance(item, Episode):
        identifier, scrape_type, imdb_id = f":{item.parent.number}:{item.number}", "series", item.parent.parent.imdb_id
    elif isinstance(item, Movie):
        identifier, scrape_type, imdb_id = None, "movie", item.imdb_id
    else:
        return None, None, None
    return identifier, scrape_type, imdb_id
