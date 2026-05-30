"""
State machine for pipeline services.

Scrape fan-out: show/season pack jobs enqueue child season/episode scrape events after
the pack completes (emitted_by == Scraping). Download does not fan-out: a Scraped
season/movie/episode is one downloader job; season packs match multiple episodes in
Downloader.match_file_to_item.
"""

from typing import Any, Literal
from kink import di
from loguru import logger

from program.media import MediaItem, States
from program.pipeline.restore_targets import scrape_queue_target
from program.types import ProcessedEvent, Service
from program.media.item import Episode, Season, Show


def process_event(
    emitted_by: Service | Literal["StateTransition", "RetryLibrary"] | str,
    existing_item: MediaItem | None = None,
    content_item: MediaItem | None = None,
    overrides: dict[str, Any] | None = None,
) -> ProcessedEvent:
    """Process an event and return the updated item, next service and items to submit."""

    from program.program import Program

    services = di[Program].services

    assert services

    next_service: Service | None = None
    no_further_processing = ProcessedEvent(
        service=None,
        related_media_items=[],
    )
    items_to_submit = list[MediaItem]()

    if existing_item and existing_item.last_state in [States.Paused, States.Failed]:
        return no_further_processing

    # Unreleased items have no actionable pipeline step — they're waiting for an air date.
    # The scheduler handles them via reindex_show tasks; re-queuing here would cause a
    # tight infinite loop ("no transition; re-queued" spam).
    if existing_item and existing_item.last_state == States.Unreleased:
        return no_further_processing

    if content_item or (
        existing_item
        and existing_item.last_state in (States.Requested, States.Unknown)
    ):
        log_string = None

        if existing_item:
            log_string = existing_item.log_string
        elif content_item:
            log_string = content_item.log_string

        logger.debug(f"Submitting {log_string} to IndexerService")

        related_media_items = list[MediaItem]()

        if content_item:
            related_media_items.append(content_item)
        elif existing_item:
            related_media_items.append(existing_item)

        return ProcessedEvent(
            service=services.indexer,
            related_media_items=related_media_items,
            overrides=overrides,
        )

    elif existing_item and existing_item.last_state in [
        States.PartiallyCompleted,
        States.Ongoing,
    ]:
        if isinstance(existing_item, Show):
            incomplete_seasons = [
                s
                for s in existing_item.seasons
                if s.last_state not in [States.Completed, States.Unreleased]
            ]

            for season in incomplete_seasons:
                processed_event = process_event(
                    emitted_by, season, None, overrides
                )

                if processed_event.related_media_items:
                    items_to_submit += processed_event.related_media_items
        elif isinstance(existing_item, Season):
            # Exclude Unreleased episodes: they have no actionable pipeline step and
            # including them causes the fan-out to return an empty items_to_submit list,
            # which triggers the "no transition; re-queued" loop in program.run.
            incomplete_episodes = [
                e for e in existing_item.episodes
                if e.last_state not in [States.Completed, States.Unreleased]
            ]

            for episode in incomplete_episodes:
                processed_event = process_event(
                    emitted_by, episode, None, overrides
                )

                if processed_event.related_media_items:
                    items_to_submit += processed_event.related_media_items

    elif existing_item and existing_item.last_state == States.Indexed:
        next_service = services.scraping

        if isinstance(existing_item, Show):
            if emitted_by != services.scraping and (
                overrides is not None
                or services.scraping.should_submit(existing_item)
            ):
                # Try pack-level scraping first when not already coming from scraper
                items_to_submit = [existing_item]
            else:
                # After pack scraping (or when emitted by scraper), submit individual seasons
                items_to_submit = [
                    s
                    for s in existing_item.seasons
                    if s.last_state
                    in [States.Indexed, States.PartiallyCompleted, States.Unknown]
                    and (
                        overrides is not None
                        or services.scraping.should_submit(s)
                    )
                ]
        elif isinstance(existing_item, Season):
            if emitted_by != services.scraping and (
                overrides is not None
                or services.scraping.should_submit(existing_item)
            ):
                # Try season-level (pack) scraping first
                items_to_submit = [existing_item]
            else:
                # After season pack scraping, submit individual episodes
                from program.db import db_functions
                from program.services.scrapers.episode_streams import (
                    _loaded_relationship,
                    episode_should_skip_scrape,
                    inherit_parent_streams_for_episode,
                )

                items_to_submit = list[MediaItem]()
                season = existing_item
                show = _loaded_relationship(season, "parent")
                if show is None and season.parent_id:
                    loaded = db_functions.get_item_by_id(season.parent_id)
                    if isinstance(loaded, Show):
                        show = loaded

                for e in existing_item.episodes:
                    if e.last_state not in [States.Indexed, States.Unknown]:
                        continue
                    if overrides is None:
                        if episode_should_skip_scrape(e):
                            continue
                        inherit_parent_streams_for_episode(
                            e, season=season, show=show
                        )
                        if e.is_scraped():
                            continue
                    if overrides is not None or services.scraping.should_submit(e):
                        items_to_submit.append(e)
        elif isinstance(existing_item, Episode):
            target = scrape_queue_target(
                existing_item, services.scraping, overrides=overrides
            )
            if target is not None:
                items_to_submit = [target]
        elif emitted_by != services.scraping and (
            overrides is not None
            or services.scraping.should_submit(existing_item)
        ):
            items_to_submit = [existing_item]

    elif existing_item and existing_item.last_state == States.Scraped:
        next_service = services.downloader
        items_to_submit = [existing_item]

    elif existing_item and existing_item.last_state == States.Downloaded:
        next_service = services.filesystem
        items_to_submit = [existing_item]

    elif existing_item and existing_item.last_state == States.Symlinked:
        next_service = services.updater
        items_to_submit = [existing_item]

    elif existing_item and existing_item.last_state == States.Completed:
        # Avoid multiple post-processing runs
        if emitted_by != services.post_processing:
            next_service = services.post_processing
            items_to_submit = [existing_item]
        else:
            return no_further_processing

    if items_to_submit:
        service_name = (
            next_service.__class__.__name__ if next_service else "StateTransition"
        )

        logger.debug(
            f"State transition complete: {len(items_to_submit)} items queued for {service_name}"
        )

    return ProcessedEvent(
        service=next_service,
        related_media_items=items_to_submit,
        overrides=overrides,
    )
