"""Inherit show/season pack streams onto episodes to skip redundant scrapes."""

from __future__ import annotations

from loguru import logger

from program.media.item import Episode, MediaItem, Season, Show
from program.media.stream import Stream
from program.services.downloaders.shared import parse_filename
from program.services.scrapers.shared import torrent_covers_episode


def _stream_blacklisted_for_episode(
    stream: Stream,
    episode: Episode,
    *,
    show: Show | None,
    season: Season | None,
) -> bool:
    if stream in episode.blacklisted_streams:
        return True
    if season is not None and stream in season.blacklisted_streams:
        return True
    if show is not None and stream in show.blacklisted_streams:
        return True
    return False


def _link_matching_streams(
    episode: Episode,
    source: MediaItem,
    *,
    show: Show | None,
    season: Season | None,
    seen_infohashes: set[str],
) -> int:
    if not source.is_scraped():
        return 0

    linked = 0
    for stream in source.streams:
        infohash = stream.infohash.lower()
        if infohash in seen_infohashes:
            continue
        if stream in episode.streams:
            seen_infohashes.add(infohash)
            continue
        if _stream_blacklisted_for_episode(
            stream, episode, show=show, season=season
        ):
            continue

        try:
            parsed = parse_filename(stream.raw_title)
        except Exception:
            continue

        if not torrent_covers_episode(parsed, episode):
            continue

        episode.streams.append(stream)
        seen_infohashes.add(infohash)
        linked += 1

    return linked


def inherit_parent_streams_for_episode(episode: Episode) -> int:
    """
    Link show/season pack streams that cover this episode onto episode.streams.

    Show is checked first (complete-series packs). Returns count of newly linked streams.
    """

    season = episode.parent
    show = episode.top_parent if season is not None else None
    seen_infohashes = {
        s.infohash.lower() for s in episode.streams if s.infohash
    }
    linked = 0

    if show is not None:
        n = _link_matching_streams(
            episode, show, show=show, season=season, seen_infohashes=seen_infohashes
        )
        if n:
            logger.debug(
                f"Inherited {n} show pack stream(s) onto {episode.log_string}"
            )
        linked += n

    if season is not None:
        n = _link_matching_streams(
            episode, season, show=show, season=season, seen_infohashes=seen_infohashes
        )
        if n:
            logger.debug(
                f"Inherited {n} season pack stream(s) onto {episode.log_string}"
            )
        linked += n

    return linked


def episode_should_skip_scrape(episode: Episode) -> bool:
    """True when the episode already has media on disk / VFS and should not scrape."""

    if episode.filesystem_entry is not None or episode.available_in_vfs:
        return True
    return False
