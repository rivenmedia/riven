"""Shared functions for scrapers."""

from datetime import datetime
from typing import Dict, Set

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.stream import Stream
from program.settings.manager import settings_manager
from program.settings.versions import models
from RTN import RTN, Torrent, sort_torrents
from RTN.exceptions import GarbageTorrent
from utils.ignore import get_ignore_hashes
from utils.logger import logger

settings_model = settings_manager.settings.ranking
ranking_model = models.get(settings_model.profile)
rtn = RTN(settings_model, ranking_model, 0.821)


def _get_stremio_identifier(item: MediaItem) -> str:
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


def _parse_results(item: MediaItem, results: Dict[str, str]) -> Dict[str, Stream]:
    """Parse the results from the scrapers into Torrent objects."""
    torrents: Set[Torrent] = set()
    processed_infohashes: Set[str] = set()
    correct_title: str = item.get_top_title()
    ignore_hashes: set = get_ignore_hashes()

    logger.log("SCRAPER", f"Processing {len(results)} results for {item.log_string}")

    if isinstance(item, Show):
        needed_seasons = [season.number for season in item.seasons]

    for infohash, raw_title in results.items():
        if infohash in processed_infohashes:
            continue

        try:
            torrent: Torrent = rtn.rank(
                raw_title=raw_title,
                infohash=infohash,
                correct_title=correct_title,
                remove_trash=True
            )

            if not torrent or not torrent.fetch:
                continue

            if isinstance(item, Movie):
                if hasattr(item, "aired_at"):
                    # If the item has an aired_at date and it's not in the future, we can check the year
                    if item.aired_at <= datetime.now() and item.aired_at.year == torrent.data.year:
                        torrents.add(torrent)
                else:
                    # This is a questionable move. 
                    torrents.add(torrent)

            elif isinstance(item, Show):
                if not needed_seasons:
                    logger.error(f"No seasons found for {item.log_string}")
                    break
                if (
                    hasattr(torrent.data, "season")
                    and len(torrent.data.season) >= (len(needed_seasons) - 1)
                    and (
                        not hasattr(torrent.data, "episode")
                        or len(torrent.data.episode) == 0
                    )
                    or torrent.data.is_complete
                ):
                    torrents.add(torrent)

            elif isinstance(item, Season):
                if (
                    len(getattr(torrent.data, "season", [])) == 1
                    and item.number in torrent.data.season
                    and (
                        not hasattr(torrent.data, "episode")
                        or len(torrent.data.episode) == 0
                    )
                    or torrent.data.is_complete
                ):
                    torrents.add(torrent)

            elif isinstance(item, Episode) and (
                item.number in torrent.data.episode
                and (
                    not hasattr(torrent.data, "season")
                    or item.parent.number in torrent.data.season
                )
                or torrent.data.is_complete
            ):
                torrents.add(torrent)

            processed_infohashes.add(infohash)

        except (ValueError, AttributeError):
            # logger.error(f"Failed to parse: '{raw_title}' - {e}")
            continue
        except GarbageTorrent:
            # logger.debug(f"Trashing torrent {infohash}: '{raw_title}'")
            continue

    if torrents:
        logger.log("SCRAPER", f"Processed {len(torrents)} matches for {item.log_string}")
        torrents = sort_torrents(torrents)
        torrents_dict = {}
        for torrent in torrents.values():
            stream = Stream(torrent)
            if torrent.infohash in ignore_hashes:
                logger.debug(f"Marking Torrent {torrent.infohash} as blacklisted for item {item.log_string}")
                item.blacklisted_streams.append(stream)
                continue
            torrents_dict[torrent.infohash] = stream
        return torrents_dict

    return {}
