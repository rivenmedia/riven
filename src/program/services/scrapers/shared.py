"""Shared functions for scrapers."""

from datetime import datetime
from loguru import logger
from RTN import RTN, ParsedData, Torrent, sort_torrents, DefaultRanking

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.stream import Stream
from program.settings import settings_manager
from program.settings.models import RTNSettingsModel, ScraperModel

# Alias to avoid changing all usages, though this might be stale if settings reload
ranking_settings = settings_manager.settings.ranking
scraping_settings = settings_manager.settings.scraping

# Global RTN instance for general parsing availability
rtn = RTN(ranking_settings, DefaultRanking())


def _apply_ranking_overrides(overrides: dict) -> RTNSettingsModel:
    """Apply user ranking overrides to create a new settings instance."""
    # Start with a fresh deep copy
    settings = ranking_settings.model_copy(deep=True)

    # 1. Resolutions
    if "resolutions" in overrides:
        wanted = set(overrides["resolutions"])
        for f in settings.resolutions.model_fields:
            setattr(settings.resolutions, f, f in wanted)

    # 2. Custom Ranks
    for key in settings.custom_ranks.model_fields:
        if key in overrides:
            wanted = set(overrides[key])
            group = getattr(settings.custom_ranks, key)
            for f in group.model_fields:
                getattr(group, f).fetch = f in wanted

    # 3. Lists
    if "require" in overrides:
        settings.require = overrides["require"] or []
    if "exclude" in overrides:
        settings.exclude = overrides["exclude"] or []
    
    return settings


def parse_results(
    item: MediaItem,
    results: dict[str, str],
    relaxed_validation: bool = False,
    overrides: dict | None = None,
    max_bitrate_override: int | None = None,
) -> dict[str, Stream]:
    """
    Parse results using RTN.

    Args:
        item: The MediaItem being parsed.
        results: Dictionary of magnet hashes to raw titles.
        relaxed_validation: If True, use permissive validation (no strict year/country checks).
    """
    if not results:
        return {}

    torrents = set[Torrent]()
    processed_infohashes = set[str]()
    correct_title = item.top_title
    if country := _get_item_country(item):
        correct_title += f" {country}"

    # Apply ranking overrides if present
    if overrides:
        effective_settings = _apply_ranking_overrides(overrides)
    else:
        effective_settings = ranking_settings
    rtn_instance = RTN(effective_settings, DefaultRanking())

    aliases = (
        {k: v for k, v in a.items() if k not in effective_settings.languages.exclude}
        if scraping_settings.enable_aliases and (a := item.get_aliases())
        else {}
    )

    logger.debug(
        f"Parsing {len(results)} results for {item.log_string} "
        f"(relaxed={relaxed_validation}, overrides={'yes' if overrides else 'no'})"
    )

    for infohash, raw_title in results.items():
        if infohash in processed_infohashes:
            continue

        try:
            torrent = rtn_instance.rank(
                raw_title=raw_title,
                infohash=infohash,
                correct_title=correct_title,
                remove_trash=(
                    getattr(effective_settings.options, "remove_all_trash", False)
                    if not relaxed_validation
                    else False
                ),
                aliases=aliases,
            )


            if not _check_item_year(item, torrent.data.year, strict=not relaxed_validation):
                continue

            if not relaxed_validation and not torrent.fetch:
                logger.trace(f"Skipping torrent (fetch=False): {raw_title} | Res: {torrent.data.resolution}")
                continue

            torrents.add(torrent)
            processed_infohashes.add(infohash)
        except Exception as e:
            logger.trace(f"GarbageTorrent: {e}")
            processed_infohashes.add(infohash)
            continue

    if torrents:
        logger.debug(f"Found {len(torrents)} streams for {item.log_string}")

        sorted_torrents = sort_torrents(
            torrents,
            bucket_limit=scraping_settings.bucket_limit if not relaxed_validation else 0,
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

def _check_item_year(
    item: MediaItem, result_year: int | None, strict: bool = True
) -> bool:
    """Check if the year matches."""
    if not strict:
        return True

    if not item.year or not result_year:
        return True

    # Allow 1 year difference
    diff = abs(item.year - result_year)
    if diff <= 1:
        return True

    return False
