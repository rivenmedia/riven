"""Resolve scrape queue targets for TV episodes (pack-first on restore/transition)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from program.media.state import States

if TYPE_CHECKING:
    from program.media.item import Episode, MediaItem
    from program.services.scrapers import Scraping


def pack_scrape_not_attempted(item: "MediaItem") -> bool:
    """True when no scrape attempt has been recorded on this item."""

    from program.utils import naive_local_datetime

    return naive_local_datetime(item.scraped_at) is None


def scrape_queue_target(
    episode: "Episode",
    scraping: "Scraping",
    *,
    overrides: dict[str, Any] | None = None,
) -> "MediaItem | None":
    """
    Pick show, season, or episode for scrape-stage queueing.

    Prefer pack scrape on an Indexed parent that has never been scraped; otherwise
    the episode when scrape cooldown allows.
    """

    if overrides is not None:
        return episode if scraping.should_submit(episode) else None

    season = episode.parent
    show = season.parent if season is not None else None

    if (
        show is not None
        and show.last_state == States.Indexed
        and pack_scrape_not_attempted(show)
        and scraping.should_submit(show)
    ):
        return show

    if (
        season is not None
        and season.last_state == States.Indexed
        and pack_scrape_not_attempted(season)
        and scraping.should_submit(season)
    ):
        return season

    return episode if scraping.should_submit(episode) else None


def scrape_restore_target_id(
    session: Session,
    episode_id: int,
    scraping: "Scraping",
) -> int | None:
    """Load episode parents and return the coalesced scrape target id, if any."""

    from program.media.item import Episode, Season

    episode = session.execute(
        select(Episode)
        .options(selectinload(Episode.parent).selectinload(Season.parent))
        .where(Episode.id == episode_id)
    ).scalar_one_or_none()

    if episode is None:
        return None

    target = scrape_queue_target(episode, scraping, overrides=None)

    return int(target.id) if target is not None else None
