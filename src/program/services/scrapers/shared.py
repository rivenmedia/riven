"""Shared functions for scrapers."""

from typing import Dict, Optional, Set

from loguru import logger
from RTN import (
    RTN,
    BaseRankingModel,
    DefaultRanking,
    ParsedData,
    Torrent,
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

# TMDB ISO 639-1 and ISO 639-2/T language codes to RTN language markers
# Supports both 2-letter (en, ja) and 3-letter (eng, jpn) language codes from TMDB
TMDB_LANGUAGE_MAP = {
    # English
    "en": "ENGLISH",
    "eng": "ENGLISH",
    # Japanese
    "ja": "JAPANESE",
    "jpn": "JAPANESE",
    # Spanish
    "es": "SPANISH",
    "spa": "SPANISH",
    # French
    "fr": "FRENCH",
    "fra": "FRENCH",
    "fre": "FRENCH",
    # German
    "de": "GERMAN",
    "deu": "GERMAN",
    "ger": "GERMAN",
    # Italian
    "it": "ITALIAN",
    "ita": "ITALIAN",
    # Portuguese
    "pt": "PORTUGUESE",
    "por": "PORTUGUESE",
    # Russian
    "ru": "RUSSIAN",
    "rus": "RUSSIAN",
    # Korean
    "ko": "KOREAN",
    "kor": "KOREAN",
    # Chinese
    "zh": "CHINESE",
    "zho": "CHINESE",
    "chi": "CHINESE",
    # Thai
    "th": "THAI",
    "tha": "THAI",
    # Arabic
    "ar": "ARABIC",
    "ara": "ARABIC",
    # Hindi
    "hi": "HINDI",
    "hin": "HINDI",
    # Polish
    "pl": "POLISH",
    "pol": "POLISH",
}

# Markers that indicate language info present or overrides in the title
EXPLICIT_LANGUAGE_MARKERS = {
    # English markers
    "english": "en",
    "eng": "en",
    "english audio": "en",
    "english dub": "en",
    "english dubbed": "en",
    # Non-English markers that should override default
    "japanese": "ja",
    "jpn": "ja",
    "japanese audio": "ja",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "russian": "ru",
    "korean": "ko",
    "chinese": "zh",
    "mandarin": "zh",
}

# Markers that indicate mixed audio/language content (should be unknown)
MIXED_LANGUAGE_MARKERS = [
    "dual audio",
    "dual.audio",
    "multi audio",
    "multi.audio",
    "multi-language",
    "multilingual",
    "eng+jpn",
    "en+jp",
]

# Markers that indicate subtitle-only or non-English only
SUBTITLE_ONLY_MARKERS = [
    "sub only",
    "sub.only",
    "subs only",
    "subs.only",
    "jp only",
    "jp.only",
    "japanese only",
    "jpn only",
    "no dub",
    "no.dub",
]

ANIME_DUB_KEYWORDS = [
    # Dual/Multi Audio
    "dual audio",
    "dual.audio",
    "multi audio",
    "multi.audio",
    "multi-audio",
    "bilingual",
    "2.0",  # Often indicates dual language audio
    "2 audio",
    "2.0 audio",
    # English Dub Keywords
    "eng dub",
    "english dub",
    "english dubbed",
    "dubbed",
    "eng.dub",
    "en.dub",
    "engdub",
    "engsub",
    "eng sub",
    "english sub",
    # Multi-language indicators
    "eng+jpn",
    "en+jp",
    "engjap",
    "eng_jap",
    "english_japanese",
    "jpn eng",
    # Subtitle indicators (for sign/song subs or forced subs)
    "signs songs",
    "signs.songs",
    "signs&songs",
    "signs and songs",
    "forced sub",
    "forced.sub",
    "forced.subtitles",
    "hardsub",
    "hardsubs",
    # Uncensored (often indicates TV vs censored version)
    "uncensored",
    "uncensor",
    # Edition indicators
    "tv edit",
    "broadcast",
]

ANIME_SUB_ONLY_KEYWORDS = [
    # Japanese only indicators
    "sub only",
    "sub.only",
    "subs only",
    "subs.only",
    "japanese only",
    "jpn only",
    "jp only",
    "jp.only",
    # Japanese audio only
    "japanese audio",
    "jp audio",
    "jpn audio",
    "japanese.audio",
    "jp.audio",
    "jpn.audio",
    "jap.audio",
    # No dub indicators
    "no dub",
    "no.dub",
    "no-dub",
    "nodub",
    "not dubbed",
    "jap sub",
    "jpn sub",
    "jp sub",
]

FALLBACK_PRIORITY_KEYWORDS = [
    "complete",
    "collection",
    "bundle",
    "pack",
    "dub",
    "dual audio",
    "english dub",
]


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


def _extract_language_from_title(title: str) -> Optional[str]:
    """Extract language markers from title.

    Returns language code if explicit markers found (e.g., 'en', 'ja', 'mixed').
    Returns 'unknown' if has mixed/subtitle-only indicators.
    Returns None if no explicit markers.
    """
    title_lower = title.lower()

    # Check for mixed language indicators (should be unknown)
    for marker in MIXED_LANGUAGE_MARKERS:
        if marker in title_lower:
            logger.debug(f"Detected mixed language marker '{marker}' in: {title}")
            return "mixed"

    # Check for subtitle-only indicators
    for marker in SUBTITLE_ONLY_MARKERS:
        if marker in title_lower:
            logger.debug(f"Detected subtitle-only marker '{marker}' in: {title}")
            return "subtitle_only"

    # Check for explicit language markers
    for marker, lang_code in EXPLICIT_LANGUAGE_MARKERS.items():
        if marker in title_lower:
            logger.debug(
                f"Detected explicit language marker '{marker}' ({lang_code}) in: {title}"
            )
            return lang_code

    return None


def _enrich_title_with_language(raw_title: str, item: MediaItem) -> str:
    """Enrich title with language markers for RTN parsing.

    Priority order:
    1. Explicit language markers in title (dub, sub, dual audio, etc) - use as-is
    2. TMDB release language - append marker if no explicit markers (if enabled)
    3. Fall back to no marker (will be unknown_language in RTN)

    Returns enriched title that RTN can parse for language detection.
    """
    # Check if language enrichment is enabled in settings
    if not scraping_settings.enrich_title_with_release_language:
        return raw_title

    # Check if title already has explicit language markers
    title_lang = _extract_language_from_title(raw_title)

    if title_lang == "mixed":
        # Mixed audio/language - leave as-is, RTN should parse as "MULTI" or unknown
        logger.debug(f"Leaving mixed-language title unchanged: {raw_title}")
        return raw_title
    elif title_lang == "subtitle_only":
        # Subtitle only - could mean non-English dub + subs
        # Leave as-is for RTN to handle; if it's anime, dub filtering will catch it
        logger.debug(f"Leaving subtitle-only title unchanged: {raw_title}")
        return raw_title
    elif title_lang:
        # Has explicit language marker (e.g., "english", "japanese")
        # Leave as-is since it's already annotated
        logger.debug(f"Title has explicit language marker ({title_lang}): {raw_title}")
        return raw_title

    # No explicit markers - check TMDB release language
    release_lang = _get_item_release_language(item)
    if release_lang:
        if release_lang in TMDB_LANGUAGE_MAP:
            language_marker = TMDB_LANGUAGE_MAP[release_lang]
            enriched_title = f"{raw_title} {language_marker}"
            logger.debug(
                f"Enriched title with TMDB release language ({release_lang}): "
                f"{raw_title} → {enriched_title}"
            )
            return enriched_title
        else:
            # release_lang exists but not in TMDB_LANGUAGE_MAP
            logger.debug(
                f"TMDB release language '{release_lang}' not in mapping for: {raw_title}"
            )
            return raw_title

    # No TMDB language data - return as-is (will result in unknown_language)
    logger.debug(
        f"No language markers or TMDB data for: {raw_title} (item.language={getattr(item, 'language', 'N/A')}, item.type={item.type})"
    )
    return raw_title


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
    remove_trash_default = settings_manager.settings.ranking.options["remove_all_trash"]

    rejection_reasons = {}  # Track why each torrent is rejected

    for infohash, raw_title in results.items():
        if infohash in processed_infohashes:
            continue

        try:
            # Enrich title with language markers before RTN parsing
            enriched_title = _enrich_title_with_language(raw_title, item)
            if enriched_title != raw_title:
                logger.info(f"[LANG_ENRICHED] {raw_title} → {enriched_title}")

            try:
                torrent: Torrent = rtn.rank(
                    raw_title=enriched_title,
                    infohash=infohash,
                    correct_title=correct_title,
                    remove_trash=remove_trash_default,
                    aliases=aliases,
                )
                logger.debug(
                    f"RTN parsed {item.log_string} torrent: episodes={torrent.data.episodes}, "
                    f"seasons={torrent.data.seasons}, year={torrent.data.year}, "
                    f"country={torrent.data.country}, dubbed={torrent.data.dubbed}: {raw_title}"
                )
            except GarbageTorrent as e:
                if remove_trash_default and _should_retry_without_trash(
                    item, raw_title, aliases
                ):
                    try:
                        torrent = rtn.rank(
                            raw_title=enriched_title,
                            infohash=infohash,
                            correct_title=correct_title,
                            remove_trash=False,
                            aliases=aliases,
                        )
                        logger.debug(
                            f"Accepted fallback torrent using keyword boost for {item.log_string}: "
                            f"episodes={torrent.data.episodes}, seasons={torrent.data.seasons}: {raw_title}"
                        )
                    except GarbageTorrent as fallback_error:
                        if log_msg:
                            logger.trace(f"GarbageTorrent (fallback): {fallback_error}")
                        rejection_reasons[raw_title] = (
                            f"GarbageTorrent (fallback): {fallback_error}"
                        )
                        processed_infohashes.add(infohash)
                        continue
                else:
                    if log_msg:
                        logger.trace(f"GarbageTorrent: {e}")
                    rejection_reasons[raw_title] = f"GarbageTorrent: {e}"
                    processed_infohashes.add(infohash)
                    continue

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
                # Enhanced dubbed anime filtering prioritizing English dub + signs/songs subtitles
                is_dubbed = False
                dub_reason = None

                # Primary check: RTN detected dubbed flag
                if torrent.data.dubbed:
                    is_dubbed = True
                    dub_reason = "RTN dubbed flag"

                # Enhanced checks for dual audio and english dub indicators
                title_lower = raw_title.lower()

                # Strong dub indicators (including signs/songs versions)
                for indicator in ANIME_DUB_KEYWORDS:
                    if indicator in title_lower:
                        is_dubbed = True
                        dub_reason = f"Dub keyword: {indicator}"
                        break

                # Sub-only exclusions (stronger filtering) - but allow signs/songs
                for indicator in ANIME_SUB_ONLY_KEYWORDS:
                    if indicator in title_lower:
                        # Don't exclude if it has signs/songs indicators
                        has_signs = any(
                            signs in title_lower
                            for signs in [
                                "signs songs",
                                "signs.songs",
                                "forced sub",
                                "forced.sub",
                            ]
                        )
                        if not has_signs:
                            is_dubbed = False
                            dub_reason = f"Sub-only keyword: {indicator}"
                            logger.trace(
                                f"Skipping sub-only anime torrent (found '{indicator}') for {item.log_string}: {raw_title}"
                            )
                            break

                # Final filter: skip if not dubbed
                if not is_dubbed:
                    rejection_reasons[raw_title] = (
                        f"Not dubbed anime (dubbed={torrent.data.dubbed}, reason={dub_reason or 'no dub indicators'})"
                    )
                    logger.trace(
                        f"Skipping non-dubbed anime torrent for {item.log_string}: {raw_title}"
                    )
                    continue

            torrents.add(torrent)
            processed_infohashes.add(infohash)
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


def _should_retry_without_trash(
    item: MediaItem, raw_title: str, aliases: Dict[str, list[str]]
) -> bool:
    """Determine whether to retry ranking without trash filtering based on keyword matches."""

    raw_lower = raw_title.lower()

    title_tokens = {item.get_top_title().lower()} if item.get_top_title() else set()
    if item.title:
        title_tokens.add(item.title.lower())

    for values in aliases.values():
        for alias in values:
            if alias:
                title_tokens.add(alias.lower())

    if not any(token and token in raw_lower for token in title_tokens):
        return False

    if any(keyword in raw_lower for keyword in FALLBACK_PRIORITY_KEYWORDS):
        return True

    if item.type == "season":
        season_tokens = {f"s{item.number:02}", f"season {item.number}"}
        if any(token in raw_lower for token in season_tokens):
            return True
    elif item.type == "show":
        season_tokens = {
            token
            for season in getattr(item, "seasons", [])
            for token in (f"s{season.number:02}", f"season {season.number}")
        }
        if any(token in raw_lower for token in season_tokens if token):
            return True

    if item.is_anime and scraping_settings.dubbed_anime_only:
        if any(keyword in raw_lower for keyword in ANIME_DUB_KEYWORDS):
            return True

    return False


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
