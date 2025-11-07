"""Shared functions for scrapers."""

from typing import Dict, Optional, Set

from loguru import logger
from RTN import (
    RTN,
    BaseRankingModel,
    DefaultRanking,
    ParsedData,
    Torrent,
    check_fetch,
    get_lev_ratio,
    get_rank,
    parse,
    sort_torrents,
)
from RTN.exceptions import GarbageTorrent

from program.media.item import MediaItem
from program.media.stream import Stream
from program.settings.manager import settings_manager
from program.settings.models import RTNSettingsModel, ScraperModel

scraping_settings: ScraperModel = settings_manager.settings.scraping
ranking_settings: RTNSettingsModel = settings_manager.settings.ranking
ranking_model: BaseRankingModel = DefaultRanking()
rtn = RTN(ranking_settings, ranking_model)

# TMDB ISO 639-1 and ISO 639-2/T language codes mapped to ISO 639-1 (used by PTT)
# This allows TMDB language data to be injected into PTT's language detection
TMDB_LANGUAGE_MAP = {
    # English
    "en": "en",
    "eng": "en",
    # Japanese
    "ja": "ja",
    "jpn": "ja",
    # Spanish
    "es": "es",
    "spa": "es",
    # French
    "fr": "fr",
    "fra": "fr",
    "fre": "fr",
    # German
    "de": "de",
    "deu": "de",
    "ger": "de",
    # Italian
    "it": "it",
    "ita": "it",
    # Portuguese
    "pt": "pt",
    "por": "pt",
    # Russian
    "ru": "ru",
    "rus": "ru",
    # Korean
    "ko": "ko",
    "kor": "ko",
    # Chinese
    "zh": "zh",
    "zho": "zh",
    "chi": "zh",
    # Thai
    "th": "th",
    "tha": "th",
    # Arabic
    "ar": "ar",
    "ara": "ar",
    # Hindi
    "hi": "hi",
    "hin": "hi",
    # Polish
    "pl": "pl",
    "pol": "pl",
}


def _enrich_parsed_data_with_tmdb_language(
    parsed_data: ParsedData, item: MediaItem
) -> None:
    """Enrich parsed data with TMDB language after PTT parsing but before ranking.

    PTT's native language detection takes priority. This only adds TMDB language
    if PTT found no language markers in the title.

    Modifies parsed_data.languages in place so ranking can evaluate it.

    Args:
        parsed_data: ParsedData object from PTT parsing (has languages field)
        item: MediaItem with TMDB language data
    """
    # Skip if PTT already detected language(s)
    if parsed_data.languages:
        logger.debug(
            f"PTT detected language(s): {parsed_data.languages}, skipping TMDB enrichment"
        )
        return

    # Skip if enrichment is disabled
    if not scraping_settings.enrich_title_with_release_language:
        logger.debug("TMDB language enrichment disabled in settings")
        return

    # Get TMDB language
    tmdb_language = _get_item_release_language(item)
    if not tmdb_language:
        logger.debug("No TMDB language available for enrichment")
        return

    # Map TMDB code to ISO 639-1
    iso_language = TMDB_LANGUAGE_MAP.get(tmdb_language)
    if iso_language:
        parsed_data.languages = [iso_language]
        logger.debug(
            f"Added TMDB language to ParsedData for ranking: {tmdb_language} → {iso_language}"
        )
    else:
        logger.debug(f"TMDB language '{tmdb_language}' not in mapping")


def _get_item_release_language(item: MediaItem) -> Optional[str]:
    """Get the release language for an item from TMDB metadata.

    Returns the language code (e.g., 'en', 'ja') from item.language (TMDB original_language).
    For episodes/seasons, inherits from parent show.
    """
    lang = None

    # Try to get language from the item or its parent hierarchy
    if item.type == "season":
        if item.parent and hasattr(item.parent, "language"):
            lang = item.parent.language
            logger.trace(f"Got language from season parent: {lang}")
    elif item.type == "episode":
        if (
            item.parent
            and item.parent.parent
            and hasattr(item.parent.parent, "language")
        ):
            lang = item.parent.parent.language
            logger.trace(f"Got language from episode parent.parent: {lang}")
    else:
        lang = item.language
        logger.trace(f"Got language from {item.type}: {lang}")

    # If we got a language, return it
    if lang:
        return lang

    # Fallback: Try to get show from database if episode/season don't have parent language
    if item.type in ("episode", "season"):
        try:
            from program.db.db_manager import db_manager

            # For episodes, the parent show is parent.parent; for seasons, it's parent
            show_id = None
            if item.type == "episode" and item.parent and item.parent.parent:
                show_id = item.parent.parent.id
            elif item.type == "season" and item.parent:
                show_id = item.parent.id

            if show_id:
                # Query the show directly from DB for language
                show = (
                    db_manager.session.query(type(item)).filter_by(id=show_id).first()
                )
                if show and hasattr(show, "language"):
                    lang = show.language
                    logger.trace(f"Got language from DB lookup: {lang}")
        except Exception as e:
            logger.trace(f"Failed to lookup show language from DB: {e}")

    return lang if lang else None


def _sanitize_title(title: str) -> str:
    """Sanitize and normalize a title to improve parsing accuracy.
    
    This function removes scene group tags at the beginning that confuse the RTN parser,
    but preserves episode markers and international character titles.
    """
    import re
    
    sanitized = title
    
    # Remove scene group tags like [ToonsHub] at the beginning
    # Match brackets with 2-20 characters (typical for group names) but NOT episode patterns
    # This avoids matching non-ASCII titles like [Ōbārōdo]
    sanitized = re.sub(r"^\s*\[[A-Za-z0-9\-._]{2,20}\]\s*", "", sanitized)
    
    sanitized = sanitized.strip()
    
    return sanitized
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
    # we should remove keys from aliases if we are requiring a language
    if ranking_settings.languages.required and len(ranking_settings.languages.required) > 0:
        aliases = {
            k: v for k, v in aliases.items() if k in ranking_settings.languages.required
        }
    
    # For anime, add roman numeral variants as aliases to help with matching
    # (e.g., if looking for season 4, add "Title IV" as an alias)
    if item.is_anime:
        try:
            # Get season number based on item type
            season_num = None
            if item.type == "season":
                season_num = item.number
            elif item.type == "episode":
                season_num = item.parent.number if item.parent else None
            # Don't add roman numeral for shows without a specific season
            
            if season_num:
                # Convert to roman numeral
                roman_vals = [
                    (1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'),
                    (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'),
                    (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')
                ]
                temp_num = int(season_num) if isinstance(season_num, str) else season_num
                roman = ''
                for val, numeral in roman_vals:
                    count = temp_num // val
                    if count:
                        roman += numeral * count
                        temp_num -= val * count
                
                if roman:
                    # Add roman numeral variant as an alias in the item's language
                    lang_key = item.language if hasattr(item, 'language') and item.language else "en"
                    roman_title = f"{correct_title} {roman}"
                    if lang_key not in aliases:
                        aliases[lang_key] = []
                    if isinstance(aliases[lang_key], list):
                        if roman_title not in aliases[lang_key]:
                            aliases[lang_key].append(roman_title)
                    elif isinstance(aliases[lang_key], str):
                        if roman_title != aliases[lang_key]:
                            aliases[lang_key] = [aliases[lang_key], roman_title]
        except Exception as e:
            logger.trace(f"Failed to add roman numeral alias: {e}")

    logger.debug(f"Processing {len(results)} results for {item.log_string}")
    remove_trash_default = settings_manager.settings.ranking.options["remove_all_trash"]

    rejection_reasons = {}  # Track why each torrent is rejected

    for infohash, raw_title in results.items():
        # Sanitize the raw title before parsing
        sanitized_title = _sanitize_title(raw_title)

        if infohash in processed_infohashes:
            continue

        try:
            # Parse the sanitized title
            parsed_data: ParsedData = parse(sanitized_title)

            # Enrich parsed data with TMDB language so ranking can evaluate it
            _enrich_parsed_data_with_tmdb_language(parsed_data, item)

            # Calculate metrics with enriched data
            lev_ratio = 0.0
            if correct_title:
                # For comparison, we need to normalize both titles to lowercase
                # but we only do this for the comparison, not for parsing
                correct_title_lower = correct_title.lower()
                parsed_title_lower = parsed_data.parsed_title.lower() if parsed_data.parsed_title else ""
                
                # Check if parsed title starts with correct title (common with spin-offs/extras)
                # e.g., "Overlord II - Ple Ple Pleiades" starts with "Overlord II"
                if parsed_title_lower.startswith(correct_title_lower):
                    lev_ratio = 1.0
                else:
                    # Check if parsed title starts with any alias
                    matches_alias = False
                    for lang_key, alias_list in aliases.items():
                        if isinstance(alias_list, list):
                            for alias in alias_list:
                                if parsed_title_lower.startswith(alias.lower()):
                                    lev_ratio = 1.0
                                    matches_alias = True
                                    break
                        elif isinstance(alias_list, str):
                            if parsed_title_lower.startswith(alias_list.lower()):
                                lev_ratio = 1.0
                                matches_alias = True
                                break
                        if matches_alias:
                            break
                    
                    # If no prefix match, use Levenshtein ratio
                    if lev_ratio == 0.0:
                        lev_ratio = get_lev_ratio(
                            correct_title_lower,
                            parsed_title_lower,
                            rtn.lev_threshold,
                            aliases,
                        )

            # Check if torrent is fetchable with enriched data
            is_fetchable, failed_keys = check_fetch(
                parsed_data, rtn.settings, speed_mode=True
            )
            rank = get_rank(parsed_data, rtn.settings, rtn.ranking_model)

            if remove_trash_default:
                if lev_ratio < rtn.lev_threshold:
                    raise GarbageTorrent(
                        f"'{raw_title}' does not match the correct title. "
                        f"correct title: '{correct_title}', parsed title: '{parsed_data.parsed_title}'"
                    )
                if not is_fetchable:
                    raise GarbageTorrent(
                        f"'{parsed_data.raw_title}' denied by: {', '.join(failed_keys)}"
                    )
                if rank < rtn.settings.options["remove_ranks_under"]:
                    raise GarbageTorrent(
                        f"'{raw_title}' does not meet the minimum rank requirement, got rank of {rank}"
                    )

            # Create Torrent with enriched data
            torrent = Torrent(
                infohash=infohash,
                raw_title=raw_title,
                data=parsed_data,
                fetch=is_fetchable,
                rank=rank,
                lev_ratio=lev_ratio,
            )

            logger.debug(
                f"RTN parsed {item.log_string} torrent: episodes={torrent.data.episodes}, "
                f"seasons={torrent.data.seasons}, year={torrent.data.year}, "
                f"country={torrent.data.country}, dubbed={torrent.data.dubbed}, "
                f"languages={torrent.data.languages}: {raw_title}"
            )

            if item.type == "movie":
                # If movie item, disregard torrents with seasons and episodes
                if torrent.data.episodes or torrent.data.seasons:
                    rejection_reasons[raw_title] = (
                        f"Show torrent for movie (has episodes={bool(torrent.data.episodes)} or seasons={bool(torrent.data.seasons)})"
                    )
                    logger.trace(
                        f"Skipping show torrent for movie {item.log_string}: {raw_title}"
                    )
                    continue

            if item.type == "show":
                # Require at least one matching season when metadata exists, but allow partial packs
                if torrent.data.episodes and len(torrent.data.episodes) < 3:
                    rejection_reasons[raw_title] = (
                        f"Too few episodes parsed ({len(torrent.data.episodes)})"
                    )
                    logger.trace(
                        f"Skipping torrent with too few parsed episodes for {item.log_string}: {raw_title}"
                    )
                    continue

                if torrent.data.seasons:
                    show_seasons = {season.number for season in item.seasons}
                    # ensure the release covers *at least* one of the tracked seasons
                    if not show_seasons.intersection(torrent.data.seasons):
                        rejection_reasons[raw_title] = (
                            f"No matching seasons (need {show_seasons}, torrent has {torrent.data.seasons})"
                        )
                        logger.trace(
                            f"Skipping torrent missing matching seasons for {item.log_string}: {raw_title}"
                        )
                        continue

                if (
                    torrent.data.episodes
                    and not torrent.data.seasons
                    and len(item.seasons) == 1
                ):
                    wanted_episodes = {
                        episode.number for episode in item.seasons[0].episodes
                    }
                    if not wanted_episodes.intersection(torrent.data.episodes):
                        rejection_reasons[raw_title] = (
                            f"No target episodes matched (need {wanted_episodes}, torrent has {torrent.data.episodes})"
                        )
                        logger.trace(
                            f"Skipping torrent missing target episodes for {item.log_string}: {raw_title}"
                        )
                        continue

            if item.type == "season":
                if torrent.data.seasons and item.number not in torrent.data.seasons:
                    rejection_reasons[raw_title] = (
                        f"Season mismatch (need S{item.number}, torrent has {torrent.data.seasons})"
                    )
                    logger.trace(
                        f"Skipping torrent with no seasons or incorrect season number for {item.log_string}: {raw_title}"
                    )
                    continue

                if torrent.data.episodes:
                    if len(torrent.data.episodes) <= 2:
                        rejection_reasons[raw_title] = (
                            f"Too few episodes in season torrent ({len(torrent.data.episodes)})"
                        )
                        logger.trace(
                            f"Skipping torrent with too few episodes for {item.log_string}: {raw_title}"
                        )
                        continue

                    season_episode_numbers = {
                        episode.number for episode in item.episodes
                    }
                    matched = season_episode_numbers.intersection(torrent.data.episodes)
                    if not matched:
                        rejection_reasons[raw_title] = (
                            f"No season episodes matched (need {season_episode_numbers}, torrent has {torrent.data.episodes})"
                        )
                        logger.trace(
                            f"Skipping torrent missing relevant episodes for {item.log_string}: {raw_title}"
                        )
                        continue

            if item.type == "episode":
                # Disregard torrents with incorrect episode number logic:
                skip = False
                # Debug logging for episode matching
                logger.debug(
                    f"Episode matching for {item.log_string}: "
                    f"item.number={item.number}, item.absolute_number={item.absolute_number}, "
                    f"item.parent.number={item.parent.number if item.parent else 'None'}, "
                    f"torrent.data.episodes={torrent.data.episodes}, "
                    f"torrent.data.seasons={torrent.data.seasons}, "
                    f"raw_title={raw_title}"
                )

                # Check if title contains the expected season/episode in any format (S06E07, Season 3 Episode 5, Overlord III, etc.)
                title_has_expected = _check_title_contains_expected_episode(
                    raw_title, item.parent.number, item.number
                )

                # If the torrent has episodes, check both episode and season
                if torrent.data.episodes:
                    # Check episode number matches
                    episode_match = (
                        item.number in torrent.data.episodes
                        or item.absolute_number in torrent.data.episodes
                    )

                    # If torrent also has season data, verify season matches too
                    # But be lenient if the title contains the expected episode format
                    season_match = True
                    if torrent.data.seasons and item.parent:
                        season_match = item.parent.number in torrent.data.seasons

                    if not episode_match:
                        # Before skipping, check if the title itself contains the expected episode
                        if title_has_expected:
                            logger.debug(
                                f"Episode number mismatch but title contains expected season/episode format, allowing: {raw_title}"
                            )
                            skip = False
                        # For anime, be more lenient - if parsing only found episodes with no season data,
                        # and the title format looks right, accept it (indexers may have incorrect metadata)
                        elif item.is_anime and not torrent.data.seasons and item.number in torrent.data.episodes:
                            logger.debug(
                                f"Anime episode match without season data, allowing (indexer metadata may be incomplete): {raw_title}"
                            )
                            skip = False
                        else:
                            skip = True
                            rejection_reasons[raw_title] = (
                                f"Episode mismatch (need E{item.number} or abs {item.absolute_number}, torrent has {torrent.data.episodes})"
                            )
                            logger.debug(
                                f"Skipping: episode number {item.number} (absolute: {item.absolute_number}) not in parsed {torrent.data.episodes}"
                            )
                    elif not season_match:
                        # Season mismatch - but if the title has the correct format, allow it
                        if title_has_expected:
                            logger.debug(
                                f"Season mismatch in parsed data but title contains correct format, allowing: {raw_title}"
                            )
                            skip = False
                        # For anime, be lenient about season mismatches if title looks right
                        # (anime indexers often have season metadata mixed up)
                        elif item.is_anime and not torrent.data.seasons:
                            logger.debug(
                                f"Anime season mismatch but torrent has no season data, being lenient: {raw_title}"
                            )
                            skip = False
                        else:
                            skip = True
                            rejection_reasons[raw_title] = (
                                f"Season mismatch (need S{item.parent.number}, torrent has {torrent.data.seasons})"
                            )
                            logger.debug(
                                f"Skipping: season {item.parent.number} not in parsed {torrent.data.seasons}"
                            )
                # If the torrent does not have episodes, but has seasons
                elif torrent.data.seasons:
                    # Season pack with no specific episodes - should only match if searching for entire season
                    # For single episode searches, reject season packs UNLESS the title contains the specific episode
                    if item.type == "episode":
                        # Check if title has the expected episode format before rejecting
                        if title_has_expected:
                            logger.debug(
                                f"Season pack but title contains expected episode format, allowing: {raw_title}"
                            )
                            skip = False
                        else:
                            skip = True
                            rejection_reasons[raw_title] = (
                                "Season pack (no specific episodes) for single episode search"
                            )
                            logger.debug(
                                f"Skipping: season pack {torrent.data.seasons} for single episode {item.log_string}"
                            )
                    elif item.parent and item.parent.number not in torrent.data.seasons:
                        # For season searches, verify the season matches
                        skip = True
                        rejection_reasons[raw_title] = (
                            f"Season mismatch (need S{item.parent.number}, torrent has {torrent.data.seasons})"
                        )
                        logger.debug(
                            f"Skipping: parent season {item.parent.number} not in parsed {torrent.data.seasons}"
                        )
                # If metadata is missing entirely, fall back to ranked title similarity
                elif title_has_expected:
                    rejection_reasons[raw_title] = (
                        "Title contains expected season/episode format - allowing based on title match"
                    )
                    logger.debug(
                        f"Allowing torrent: title contains expected season/episode - {raw_title}"
                    )
                else:
                    rejection_reasons[raw_title] = (
                        "No episode/season metadata - allowing based on title match"
                    )
                    logger.debug(
                        f"Allowing torrent without structured episode/season data due to no RTN metadata - relying on title match: {raw_title}"
                    )

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
                    rejection_reasons[raw_title] = (
                        f"Country mismatch ({torrent.data.country} not in {_get_item_country(item)})"
                    )
                    logger.trace(
                        f"Skipping torrent for incorrect country with {item.log_string}: {raw_title}"
                    )
                    continue

            if torrent.data.year and not _check_item_year(item, torrent.data):
                # If year is present, then check to make sure it's correct
                rejection_reasons[raw_title] = f"Year mismatch ({torrent.data.year})"
                logger.debug(
                    f"Skipping torrent for incorrect year with {item.log_string}: {raw_title}"
                )
                continue

            if item.is_anime and scraping_settings.dubbed_anime_only:
                # Rely on RTN's parsed data for language and dub status.
                # The `dubbed` flag is set by PTT, and `languages` is enriched from TMDB.
                is_english_dub = torrent.data.dubbed or "en" in torrent.data.languages
                if not is_english_dub:
                    rejection_reasons[raw_title] = (
                        f"Not an English dub (dubbed={torrent.data.dubbed}, languages={torrent.data.languages})"
                    )
                    logger.trace(
                        f"Skipping non-dubbed anime torrent for {item.log_string}: {raw_title}"
                    )
                    continue

            torrents.add(torrent)
            processed_infohashes.add(infohash)
        except GarbageTorrent as e:
            # This is now the ONLY exception handler for this.
            # If RTN says it's trash, it's trash. We don't retry.
            if log_msg:
                logger.trace(f"GarbageTorrent: {e}")
            rejection_reasons[raw_title] = f"GarbageTorrent: {e}"
            processed_infohashes.add(infohash)
            continue
        except Exception as e:
            if log_msg:
                logger.trace(f"Parser error: {e}")
            rejection_reasons[raw_title] = f"Parser exception: {type(e).__name__}"
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

    # All results were filtered out - log detailed rejection report
    if results and log_msg:
        # Aggregate rejection reasons
        reason_counts = {}
        for reason in rejection_reasons.values():
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        reasons_summary = "; ".join(
            [
                f"{count}× {reason}"
                for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])
            ]
        )

        logger.warning(
            f"All {len(results)} torrents for {item.log_string} were filtered out. "
            f"Top rejection reasons: {reasons_summary}"
        )

    return {}


# helper functions


def _check_item_year(item: MediaItem, data: ParsedData) -> bool:
    """Check if the year of the torrent is within the range of the item."""
    if not item.aired_at or not data.year:
        return True

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


def _check_title_contains_expected_episode(
    raw_title: str, season_num: int, episode_num: int
) -> bool:
    """Check if raw title contains the expected season/episode in any format.

    This helps identify correct episodes even when RTN parsing differs from expected.
    Handles multiple naming conventions:
    - S##E## format (standard): S06E07
    - Roman numerals (anime): Season III Episode 7, Overlord III
    - Spelled out (anime): Season 3 Episode 7
    - Absolute numbering (anime): Episode 135
    """
    import re

    if not raw_title:
        return False

    title_upper = raw_title.upper()

    # Build pattern with word boundaries to match context
    # Pattern 1: Standard S##E## or S#E# format
    pattern_standard = (
        rf"\bS{season_num:02d}E{episode_num:02d}\b|\bS{season_num}E{episode_num}\b"
    )

    # Pattern 2: Season NUMBER Episode NUMBER (handles "Season 3 Episode 7")
    pattern_spelled = rf"\bSEASON\s+{season_num}\b.*\bEPISODE\s+{episode_num}\b"

    # Pattern 3: Roman numeral pattern (Season I, II, III, IV, V, etc.)
    # Convert season number to roman numeral
    roman_season = _arabic_to_roman(season_num)
    if roman_season:
        pattern_roman = rf"\b(?:SEASON\s+)?{roman_season}(?:\s+SEASON)?\b"
    else:
        pattern_roman = None

    # Try each pattern
    if re.search(pattern_standard, title_upper):
        return True

    if re.search(pattern_spelled, title_upper):
        return True

    # For roman numerals, just check if season roman matches
    # (more lenient since episode number might be harder to detect after roman)
    if pattern_roman and re.search(pattern_roman, title_upper):
        # Additional check: make sure episode number appears somewhere in title
        # to avoid false positives like "Overlord II" when looking for "Overlord III Episode 5"
        if re.search(rf"\b{episode_num}\b", title_upper):
            return True

    return False


def _arabic_to_roman(num: int) -> str:
    """Convert Arabic number to Roman numeral (I-X range for seasons)."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    roman_num = ""
    i = 0
    while num > 0:
        for _ in range(num // val[i]):
            roman_num += syms[i]
            num -= val[i]
        i += 1
    return roman_num if roman_num else None
