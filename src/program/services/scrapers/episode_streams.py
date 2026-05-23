"""Inherit show/season pack streams onto episodes to skip redundant scrapes."""

from __future__ import annotations

from loguru import logger
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm.base import NO_VALUE

from program.media.item import Episode, MediaItem, Season, Show
from program.media.stream import Stream
from program.services.downloaders.shared import parse_filename
from program.services.scrapers.shared import torrent_covers_episode


def _loaded_relationship(obj: MediaItem, attr_name: str) -> MediaItem | None:
    """Return a relationship value only if it is already in memory (no lazy load)."""

    state = sa_inspect(obj, raiseerr=False)
    if state is not None and getattr(state, "mapper", None):
        attr = state.attrs.get(attr_name)
        if attr is None or attr.loaded_value is NO_VALUE:
            return None
        return attr.loaded_value

    # Non-ORM test doubles: plain attribute access is safe.
    value = getattr(obj, attr_name, None)
    return value if value is not None else None


def _resolve_parents(
    episode: Episode,
    *,
    season: Season | None = None,
    show: Show | None = None,
) -> tuple[Season | None, Show | None]:
    """Resolve season/show without lazy-loading detached ORM instances."""

    if season is None:
        season = _loaded_relationship(episode, "parent")
        if season is None and episode.parent_id:
            from program.db import db_functions

            loaded = db_functions.get_item_by_id(episode.parent_id)
            if isinstance(loaded, Season):
                season = loaded

    if season is not None and show is None:
        show = _loaded_relationship(season, "parent")
        if show is None and season.parent_id:
            from program.db import db_functions

            loaded = db_functions.get_item_by_id(season.parent_id)
            if isinstance(loaded, Show):
                show = loaded

    return season, show


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


def inherit_parent_streams_for_episode(
    episode: Episode,
    *,
    season: Season | None = None,
    show: Show | None = None,
) -> int:
    """
    Link show/season pack streams that cover this episode onto episode.streams.

    Show is checked first (complete-series packs). Returns count of newly linked streams.
    """

    season, show = _resolve_parents(episode, season=season, show=show)
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


def actionable_episodes(season: Season) -> list[Episode]:
    """Episodes eligible for scrape health checks (released, indexed, not on disk)."""

    from program.media.state import States

    result: list[Episode] = []
    for episode in season.episodes:
        if episode.last_state not in (States.Indexed, States.Unknown):
            continue
        if not episode.is_released:
            continue
        if episode_should_skip_scrape(episode):
            continue
        result.append(episode)
    return result


def pack_pipeline_episodes(season: Season) -> list[Episode]:
    """Released episodes still in scrape/download pipeline (not on disk / VFS)."""

    from program.media.state import States

    result: list[Episode] = []
    for episode in season.episodes:
        if episode.last_state in (States.Paused, States.Failed):
            continue
        if not episode.is_released:
            continue
        if episode_should_skip_scrape(episode):
            continue
        result.append(episode)
    return result


def episode_scrape_attempted(episode: Episode) -> bool:
    """True when a per-episode scrape has been recorded."""

    from program.utils import naive_local_datetime

    return naive_local_datetime(episode.scraped_at) is not None


def individually_scraped_episode_counts(
    season: Season,
) -> tuple[int, int, float]:
    """
    Return (pipeline_count, individually_scraped_count, ratio) for a season.

    Counts episodes with streams or a scrape attempt, among those still not on disk.
    """

    pipeline = pack_pipeline_episodes(season)
    if not pipeline:
        return 0, 0, 0.0
    scraped = sum(
        1
        for episode in pipeline
        if episode.is_scraped() or episode_scrape_attempted(episode)
    )
    return len(pipeline), scraped, scraped / len(pipeline)


def streamless_episode_counts(
    season: Season,
) -> tuple[int, int, float]:
    """
    Return (actionable_count, streamless_count, streamless_ratio) for a season.

    Streamless means no non-blacklisted streams (same as ``is_scraped()`` false).
  """

    actionable = actionable_episodes(season)
    if not actionable:
        return 0, 0, 0.0
    streamless = sum(1 for episode in actionable if not episode.is_scraped())
    return len(actionable), streamless, streamless / len(actionable)
