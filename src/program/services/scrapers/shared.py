"""Shared functions for scrapers."""

from typing import Dict, Set

from loguru import logger
from RTN import RTN, ParsedData, Torrent, sort_torrents

from program.media.item import MediaItem
from program.media.stream import Stream
from program.settings.manager import settings_manager
from program.settings.versions import models

scraping_settings = settings_manager.settings.scraping
ranking_settings = settings_manager.settings.ranking
ranking_model = models.get(ranking_settings.profile)
rtn = RTN(ranking_settings, ranking_model)


def _parse_results(
    item: MediaItem, results: Dict[str, str], log_msg: bool = True
) -> Dict[str, Stream]:
    """Parse the results from the scrapers into Torrent objects."""
    torrents: Set[Torrent] = set()
    processed_infohashes: Set[str] = set()
    correct_title: str = item.get_top_title()

    aliases: Dict[str, list[str]] = (
        item.get_aliases() if scraping_settings.enable_aliases else {}
    )
    # we should remove keys from aliases if we are excluding the language
    aliases = {
        k: v for k, v in aliases.items() if k not in ranking_settings.languages.exclude
    }

    logger.debug(f"Processing {len(results)} results for {item.log_string}")

    for infohash, raw_title in results.items():
        if infohash in processed_infohashes:
            continue

        try:
            torrent: Torrent = rtn.rank(
                raw_title=raw_title,
                infohash=infohash,
                correct_title=correct_title,
                remove_trash=settings_manager.settings.ranking.options[
                    "remove_all_trash"
                ],
                aliases=aliases,
            )

            if item.type == "movie":
                # If movie item, disregard torrents with seasons and episodes
                if torrent.data.episodes or torrent.data.seasons:
                    logger.trace(
                        f"Skipping show torrent for movie {item.log_string}: {raw_title}"
                    )
                    continue

            if item.type == "show":
                # make sure the torrent has at least 2 episodes (should weed out most junk)
                if torrent.data.episodes and len(torrent.data.episodes) <= 2:
                    logger.trace(
                        f"Skipping torrent with too few episodes for {item.log_string}: {raw_title}"
                    )
                    continue

                # make sure all of the item seasons are present in the torrent
                if not all(
                    season.number in torrent.data.seasons for season in item.seasons
                ):
                    logger.trace(
                        f"Skipping torrent with incorrect number of seasons for {item.log_string}: {raw_title}"
                    )
                    continue

                if (
                    torrent.data.episodes
                    and not torrent.data.seasons
                    and len(item.seasons) == 1
                    and not all(
                        episode.number in torrent.data.episodes
                        for episode in item.seasons[0].episodes
                    )
                ):
                    logger.trace(
                        f"Skipping torrent with incorrect number of episodes for {item.log_string}: {raw_title}"
                    )
                    continue

            if item.type == "season":
                if torrent.data.seasons and item.number not in torrent.data.seasons:
                    logger.trace(
                        f"Skipping torrent with no seasons or incorrect season number for {item.log_string}: {raw_title}"
                    )
                    continue

                # make sure the torrent has at least 2 episodes (should weed out most junk)
                if torrent.data.episodes and len(torrent.data.episodes) <= 2:
                    logger.trace(
                        f"Skipping torrent with too few episodes for {item.log_string}: {raw_title}"
                    )
                    continue

                # disregard torrents with incorrect season number
                if item.number not in torrent.data.seasons:
                    logger.trace(
                        f"Skipping incorrect season torrent for {item.log_string}: {raw_title}"
                    )
                    continue

                if torrent.data.episodes and not all(
                    episode.number in torrent.data.episodes for episode in item.episodes
                ):
                    logger.trace(
                        f"Skipping incorrect season torrent for not having all episodes {item.log_string}: {raw_title}"
                    )
                    continue

            if item.type == "episode":
                # Disregard torrents with incorrect episode number logic:
                skip = False
                # If the torrent has episodes, but the episode number is not present
                if torrent.data.episodes:
                    if (
                        item.number not in torrent.data.episodes
                        and item.absolute_number not in torrent.data.episodes
                    ):
                        skip = True
                # If the torrent does not have episodes, but has seasons, and the parent season is not present
                elif torrent.data.seasons:
                    if item.parent.number not in torrent.data.seasons:
                        skip = True
                # If the torrent has neither episodes nor seasons, skip (junk)
                else:
                    skip = True

                if skip:
                    logger.trace(
                        f"Skipping incorrect episode torrent for {item.log_string}: {raw_title}"
                    )
                    continue

            if torrent.data.country and not item.is_anime:
                # If country is present, then check to make sure it's correct. (Covers: US, UK, NZ, AU)
                if (
                    torrent.data.country
                    and torrent.data.country not in _get_item_country(item)
                ):
                    logger.trace(
                        f"Skipping torrent for incorrect country with {item.log_string}: {raw_title}"
                    )
                    continue

            if torrent.data.year and not _check_item_year(item, torrent.data):
                # If year is present, then check to make sure it's correct
                logger.debug(
                    f"Skipping torrent for incorrect year with {item.log_string}: {raw_title}"
                )
                continue

            if item.is_anime and scraping_settings.dubbed_anime_only:
                # If anime and user wants dubbed only, then check to make sure it's dubbed
                if not torrent.data.dubbed:
                    logger.trace(
                        f"Skipping non-dubbed anime torrent for {item.log_string}: {raw_title}"
                    )
                    continue

            torrents.add(torrent)
            processed_infohashes.add(infohash)
        except Exception as e:
            if log_msg:
                logger.trace(f"GarbageTorrent: {e}")
            processed_infohashes.add(infohash)
            continue

    if torrents:
        logger.debug(f"Found {len(torrents)} streams for {item.log_string}")
        torrents = sort_torrents(torrents, bucket_limit=scraping_settings.bucket_limit)
        torrents_dict = {}
        for torrent in torrents.values():
            torrents_dict[torrent.infohash.lower()] = Stream(torrent)
        logger.debug(
            f"Kept {len(torrents_dict)} streams for {item.log_string} after processing bucket limit"
        )
        return torrents_dict

    return {}


# helper functions


def _check_item_year(item: MediaItem, data: ParsedData) -> bool:
    """Check if the year of the torrent is within the range of the item."""
    return data.year in [
        item.aired_at.year - 1,
        item.aired_at.year,
        item.aired_at.year + 1,
    ]


def _get_item_country(item: MediaItem) -> str:
    """Get the country code for a country."""
    country = ""

    if item.type == "season":
        country = item.parent.country.upper()
    elif item.type == "episode":
        country = item.parent.parent.country.upper()
    else:
        country = item.country.upper()

    # need to normalize
    if country == "USA":
        country = "US"
    elif country == "GB":
        country = "UK"

    return country
