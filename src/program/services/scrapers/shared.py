"""
Shared utilities for scraper services.

This module provides common validation and processing functions used by all scrapers:
- validate_and_store_streams: Validate and store discovered streams
- _check_item_year: Validate torrent year matches item
- _get_item_country: Get country code for item

Stream validation includes:
- Type checking (movie vs show torrents)
- Season/episode matching
- Year validation
- Country validation
- Dubbed anime filtering (optional)

All streams are stored WITHOUT ranking - ranking happens per profile in Downloader.
"""
from typing import Dict, Set

from loguru import logger
from RTN import ParsedData, Torrent, parse

from program.media.item import MediaItem
from program.media.stream import Stream
from program.settings.manager import settings_manager

scraping_settings = settings_manager.settings.scraping


def validate_and_store_streams(item: MediaItem, results: Dict[str, str], log_msg: bool = True) -> Dict[str, Stream]:
    """
    Validate and store ALL discovered streams without ranking.

    This function parses torrents and validates them against the item,
    but does NOT apply any ranking or quality filtering. All valid streams
    are stored for later ranking by the downloader per scraping profile.

    Args:
        item: MediaItem to validate streams for
        results: Dictionary of infohash -> raw_title from scrapers
        log_msg: Whether to log trace messages

    Returns:
        Dictionary of infohash -> Stream (unranked, all valid streams)
    """
    streams_dict: Dict[str, Stream] = {}
    processed_infohashes: Set[str] = set()

    logger.debug(f"Processing {len(results)} results for {item.log_string}")

    for infohash, raw_title in results.items():
        if infohash in processed_infohashes:
            continue

        try:
            # Parse the torrent WITHOUT ranking (just extract metadata)
            parsed_data: ParsedData = parse(raw_title)

            # Basic validation checks (same as before, but without ranking)
            if item.type == "movie":
                # If movie item, disregard torrents with seasons and episodes
                if parsed_data.episodes or parsed_data.seasons:
                    logger.trace(f"Skipping show torrent for movie {item.log_string}: {raw_title}")
                    continue

            if item.type == "show":
                # make sure the torrent has at least 2 episodes (should weed out most junk)
                if parsed_data.episodes and len(parsed_data.episodes) <= 2:
                    logger.trace(f"Skipping torrent with too few episodes for {item.log_string}: {raw_title}")
                    continue

                # make sure all of the item seasons are present in the torrent
                if not all(season.number in parsed_data.seasons for season in item.seasons):
                    logger.trace(f"Skipping torrent with incorrect number of seasons for {item.log_string}: {raw_title}")
                    continue

                if parsed_data.episodes and not parsed_data.seasons and len(item.seasons) == 1 and not all(episode.number in parsed_data.episodes for episode in item.seasons[0].episodes):
                    logger.trace(f"Skipping torrent with incorrect number of episodes for {item.log_string}: {raw_title}")
                    continue

            if item.type == "season":
                if parsed_data.seasons and item.number not in parsed_data.seasons:
                    logger.trace(f"Skipping torrent with no seasons or incorrect season number for {item.log_string}: {raw_title}")
                    continue

                # make sure the torrent has at least 2 episodes (should weed out most junk)
                if parsed_data.episodes and len(parsed_data.episodes) <= 2:
                    logger.trace(f"Skipping torrent with too few episodes for {item.log_string}: {raw_title}")
                    continue

                # disregard torrents with incorrect season number
                if item.number not in parsed_data.seasons:
                    logger.trace(f"Skipping incorrect season torrent for {item.log_string}: {raw_title}")
                    continue

                if parsed_data.episodes and not all(episode.number in parsed_data.episodes for episode in item.episodes):
                    logger.trace(f"Skipping incorrect season torrent for not having all episodes {item.log_string}: {raw_title}")
                    continue

            if item.type == "episode":
                # Disregard torrents with incorrect episode number logic:
                skip = False
                # If the torrent has episodes, but the episode number is not present
                if parsed_data.episodes:
                    if item.number not in parsed_data.episodes and item.absolute_number not in parsed_data.episodes:
                        skip = True
                # If the torrent does not have episodes, but has seasons, and the parent season is not present
                elif parsed_data.seasons:
                    if item.parent.number not in parsed_data.seasons:
                        skip = True
                # If the torrent has neither episodes nor seasons, skip (junk)
                else:
                    skip = True

                if skip:
                    logger.trace(f"Skipping incorrect episode torrent for {item.log_string}: {raw_title}")
                    continue

            if parsed_data.country and not item.is_anime:
                # If country is present, then check to make sure it's correct. (Covers: US, UK, NZ, AU)
                if parsed_data.country and parsed_data.country not in _get_item_country(item):
                    logger.trace(f"Skipping torrent for incorrect country with {item.log_string}: {raw_title}")
                    continue

            if parsed_data.year and not _check_item_year(item, parsed_data):
                # If year is present, then check to make sure it's correct
                logger.trace(f"Skipping torrent for incorrect year with {item.log_string}: {raw_title}")
                continue

            if item.is_anime and scraping_settings.dubbed_anime_only:
                # If anime and user wants dubbed only, then check to make sure it's dubbed
                if not parsed_data.dubbed:
                    logger.trace(f"Skipping non-dubbed anime torrent for {item.log_string}: {raw_title}")
                    continue

            # Create a minimal Torrent object without ranking
            # We'll use rank=0 and lev_ratio=0.0 as placeholders since ranking happens later
            torrent = Torrent(
                raw_title=raw_title,
                infohash=infohash,
                data=parsed_data,
                fetch=True,  # Assume fetchable by default
                rank=0,  # Placeholder - will be ranked per profile in downloader
                lev_ratio=0.0  # Placeholder - will be calculated per profile in downloader
            )

            streams_dict[infohash.lower()] = Stream(torrent)
            processed_infohashes.add(infohash)
        except Exception as e:
            if log_msg:
                logger.trace(f"GarbageTorrent: {e}")
            processed_infohashes.add(infohash)
            continue

    if streams_dict:
        logger.debug(f"Stored {len(streams_dict)} valid streams for {item.log_string} (unranked)")

    return streams_dict

def _check_item_year(item: MediaItem, data: ParsedData) -> bool:
    """
    Check if the torrent year matches the item year (±1 year tolerance).

    Args:
        item: MediaItem to check against.
        data: ParsedData from torrent.

    Returns:
        bool: True if year matches within tolerance, False otherwise.
    """
    return data.year in [item.aired_at.year - 1, item.aired_at.year, item.aired_at.year + 1]

def _get_item_country(item: MediaItem) -> str:
    """
    Get the country code for a MediaItem.

    Traverses hierarchy for seasons/episodes to get show country.
    Normalizes country codes (USA → US, GB → UK).

    Args:
        item: MediaItem to get country for.

    Returns:
        str: Normalized country code (e.g., "US", "UK").
    """
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
