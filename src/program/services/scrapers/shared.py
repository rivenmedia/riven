"""Shared functions for scrapers."""

import re
from datetime import datetime
from loguru import logger
from RTN import (
    RTN,
    ParsedData,
    Torrent,
    sort_torrents,
    BaseRankingModel,
    DefaultRanking,
)
from RTN.models import ResolutionConfig, CustomRanksConfig, CustomRank
from pydantic import BaseModel

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.stream import Stream
from program.settings import settings_manager
from program.settings.models import RTNSettingsModel, ScraperModel
from program.services.scrapers.models import RankingOverrides

scraping_settings: ScraperModel = settings_manager.settings.scraping
ranking_settings: RTNSettingsModel = settings_manager.settings.ranking
ranking_model: BaseRankingModel = DefaultRanking()
rtn = RTN(ranking_settings, ranking_model)


def tokenize_quality(quality_string: str) -> set[str]:
    """
    Tokenize a quality string into normalized tokens for exact matching.
    
    Splits on spaces, punctuation (-, _, /, .), and non-alphanumeric boundaries,
    then lowercases all tokens.
    
    Examples:
        "WEB-DL" -> {"web", "dl"}
        "BluRay REMUX" -> {"bluray", "remux"}
        "WEBDL" -> {"webdl"}
        "WEB DL" -> {"web", "dl"}
    """
    if not quality_string:
        return set()
    
    # Split on common delimiters: space, dash, underscore, slash, dot
    # Then filter out empty strings and lowercase
    tokens = re.split(r'[\s\-_/\.]+', quality_string.lower())
    return {token for token in tokens if token}


def parse_results(
    item: MediaItem,
    results: dict[str, str],
    log_msg: bool = True,
    ranking_overrides: RankingOverrides | None = None,
    manual: bool = False,
) -> dict[str, Stream]:
    """Parse the results from the scrapers into Torrent objects."""

    torrents = set[Torrent]()
    processed_infohashes = set[str]()
    correct_title = item.top_title

    aliases = (
        {k: v for k, v in a.items() if k not in ranking_settings.languages.exclude}
        if scraping_settings.enable_aliases and (a := item.get_aliases())
        else {}
    )

    logger.debug(f"Processing {len(results)} results for {item.log_string} (manual={manual}, has_overrides={ranking_overrides is not None})")

    rtn_instance = rtn

    if manual and not ranking_overrides:
        # If manual and no overrides, use permissive settings (show everything)
        overridden_settings = ranking_settings.model_copy(deep=True)

        # Enable all resolutions
        for res_key in ResolutionConfig.model_fields:
            if hasattr(overridden_settings.resolutions, res_key):
                setattr(overridden_settings.resolutions, res_key, True)

        # Clear exclude and require lists
        overridden_settings.require = []
        overridden_settings.exclude = []

        # Enable all custom ranks
        for category in CustomRanksConfig.model_fields:
            category_settings: BaseModel = getattr(
                overridden_settings.custom_ranks, category
            )

            for key in category_settings.__class__.model_fields:
                rank_obj = getattr(category_settings, key)
                rank_obj.fetch = True

        rtn_instance = RTN(overridden_settings, ranking_model)

    # Use overrides if provided, otherwise use global settings
    if ranking_overrides:
        logger.debug(
            f"Applying ranking overrides for {item.log_string}: "
            f"quality={ranking_overrides.quality}"
        )
        # Create a copy of settings with overrides
        overridden_settings = ranking_settings.model_copy(deep=True)

        # 1. Resolutions
        if (resolutions_list := ranking_overrides.resolutions) is not None:
            # Reset all to False
            for res_key in ResolutionConfig.model_fields:
                setattr(overridden_settings.resolutions, res_key, False)

            # Enable selected
            for res_key in resolutions_list:
                if hasattr(overridden_settings.resolutions, res_key):
                    setattr(overridden_settings.resolutions, res_key, True)

        # 2. Custom Ranks (quality, rips, hdr, audio, extras, trash)
        # When overrides are provided, disable ALL custom ranks first,
        # then enable only the explicitly specified ones.
        # This prevents unwanted formats (like WEB-DL) from being included
        # when user doesn't specify them.
        for category in CustomRanksConfig.model_fields:
            selected_keys = getattr(ranking_overrides, category)
            category_settings: BaseModel = getattr(
                overridden_settings.custom_ranks, category
            )

            for key in category_settings.__class__.model_fields:
                rank_obj: CustomRank = getattr(category_settings, key)

                if selected_keys is not None:
                    # User explicitly specified this category - only enable selected keys
                    rank_obj.fetch = key in selected_keys
                # If selected_keys is None, keep the user's base settings for that category

        # 3. Require / Exclude
        if ranking_overrides.require is not None:
            overridden_settings.require = ranking_overrides.require
        
        if ranking_overrides.exclude is not None:
            overridden_settings.exclude = ranking_overrides.exclude

        rtn_instance = RTN(overridden_settings, ranking_model)

    for infohash, raw_title in results.items():
        if infohash in processed_infohashes:
            continue

        try:

            torrent = rtn_instance.rank(
                raw_title=raw_title,
                infohash=infohash,
                correct_title=correct_title,
                remove_trash=(
                    settings_manager.settings.ranking.options["remove_all_trash"]
                    if not manual
                    else False
                ),
                aliases=aliases,
            )

            if isinstance(item, Movie):
                # If movie item, disregard torrents with seasons and episodes
                if not manual and (torrent.data.episodes or torrent.data.seasons):
                    logger.trace(
                        f"Skipping show torrent for movie {item.log_string}: {raw_title}"
                    )
                    continue

            if isinstance(item, Show):
                # make sure the torrent has at least 2 episodes (should weed out most junk)
                if (
                    not manual
                    and torrent.data.episodes
                    and len(torrent.data.episodes) <= 2
                ):
                    logger.trace(
                        f"Skipping torrent with too few episodes for {item.log_string}: {raw_title}"
                    )
                    continue

                # make sure all of the item seasons are present in the torrent
                if (
                    not ranking_overrides
                    and not manual
                    and not all(
                        season.number in torrent.data.seasons for season in item.seasons
                    )
                ):
                    logger.trace(
                        f"Skipping torrent with incorrect number of seasons for {item.log_string}: {raw_title}"
                    )
                    continue

                if (
                    not manual
                    and torrent.data.episodes
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

            if isinstance(item, Season):
                if (
                    not manual
                    and torrent.data.seasons
                    and item.number not in torrent.data.seasons
                ):
                    logger.trace(
                        f"Skipping torrent with no seasons or incorrect season number for {item.log_string}: {raw_title}"
                    )
                    continue

                # make sure the torrent has at least 2 episodes (should weed out most junk), skip if manual
                if (
                    not ranking_overrides
                    and not manual
                    and torrent.data.episodes
                    and len(torrent.data.episodes) <= 2
                ):
                    logger.trace(
                        f"Skipping torrent with too few episodes for {item.log_string}: {raw_title}"
                    )
                    continue

                # disregard torrents with incorrect season number
                if not manual and item.number not in torrent.data.seasons:
                    logger.trace(
                        f"Skipping incorrect season torrent for {item.log_string}: {raw_title}"
                    )
                    continue

                if torrent.data.episodes and not all(
                    episode.number in torrent.data.episodes for episode in item.episodes
                ):
                    # Skip this check if using manual overrides (user intent)
                    if not ranking_overrides and not manual:
                        logger.trace(
                            f"Skipping incorrect season torrent for not having all episodes {item.log_string}: {raw_title}"
                        )
                        continue

            if isinstance(item, Episode) and not manual:
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
                    if item.parent.number not in torrent.data.seasons:  # type: ignore
                        skip = True

                # If the torrent has neither episodes nor seasons, skip (junk)
                else:
                    skip = True

                if skip:
                    logger.trace(
                        f"Skipping incorrect episode torrent for {item.log_string}: {raw_title}"
                    )
                    continue

            if not manual and torrent.data.country and not item.is_anime:
                # If country is present, then check to make sure it's correct. (Covers: US, UK, NZ, AU)
                if (
                    torrent.data.country
                    and (item_country := _get_item_country(item))
                    and torrent.data.country not in item_country
                ):
                    logger.trace(
                        f"Skipping torrent for incorrect country with {item.log_string}: {raw_title}"
                    )
                    continue

            if (
                not manual
                and torrent.data.year
                and item.aired_at
                and not _check_item_year(item.aired_at, torrent.data)
            ):
                # If year is present, then check to make sure it's correct
                logger.trace(
                    f"Skipping torrent for incorrect year with {item.log_string}: {raw_title}"
                )
                continue

            if not manual and item.is_anime and scraping_settings.dubbed_anime_only:
                # If anime and user wants dubbed only, then check to make sure it's dubbed
                if not torrent.data.dubbed:
                    logger.trace(
                        f"Skipping non-dubbed anime torrent for {item.log_string}: {raw_title}"
                    )
                    continue

            if not torrent.fetch:
                continue

            # Enforce exclusive quality type filtering when overrides specify quality
            # If quality list is provided and torrent's quality type is NOT in the list, skip it
            # Uses tokenized exact matching to avoid substring issues (e.g., "web" matching "WEB-DL")
            if (
                ranking_overrides
                and ranking_overrides.quality is not None
                and torrent.data.quality
            ):
                # Tokenize the torrent's quality into normalized tokens
                quality_tokens = tokenize_quality(torrent.data.quality)
                # Tokenize allowed qualities (each override item is also tokenized)
                allowed_tokens = set()
                for q in ranking_overrides.quality:
                    allowed_tokens.update(tokenize_quality(q))
                
                # Check if any quality token matches an allowed token exactly
                quality_match = bool(quality_tokens & allowed_tokens)
                
                if not quality_match:
                    logger.debug(
                        f"Quality filter: Skipping '{torrent.data.quality}' (tokens: {quality_tokens}) torrent (allowed tokens: {allowed_tokens}): {raw_title}"
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

        sorted_torrents = sort_torrents(
            torrents,
            bucket_limit=scraping_settings.bucket_limit if not manual else 500,
        )

        torrent_stream_map = {
            torrent.infohash.lower(): Stream(torrent)
            for torrent in sorted_torrents.values()
        }

        logger.debug(
            f"Kept {len(torrent_stream_map)} streams for {item.log_string} after processing bucket limit"
        )

        return torrent_stream_map

    return {}


# helper functions


def _check_item_year(aired_at: datetime, data: ParsedData) -> bool:
    """Check if the year of the torrent is within the range of the item."""

    return data.year in [
        aired_at.year - 1,
        aired_at.year,
        aired_at.year + 1,
    ]


def _get_item_country(item: MediaItem) -> str | None:
    """Get the country code for a country."""

    country = None

    if isinstance(item, Season) and item.parent.country:
        country = item.parent.country.upper()
    elif isinstance(item, Episode) and item.parent.parent.country:
        country = item.parent.parent.country.upper()
    elif item.country:
        country = item.country.upper()

    if not country:
        return None

    # need to normalize
    if country == "USA":
        country = "US"
    elif country == "GB":
        country = "UK"

    return country
