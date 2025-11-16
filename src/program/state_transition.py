from typing import Literal
from kink import di
from loguru import logger

from program.media import MediaItem, States
from program.types import ProcessedEvent, Service
from program.media.item import Season, Show


def process_event(
    emitted_by: Service | Literal["StateTransition", "RetryLibrary"] | str,
    existing_item: MediaItem | None = None,
    content_item: MediaItem | None = None,
) -> ProcessedEvent:
    """Process an event and return the updated item, next service and items to submit."""

    from program.program import Program

    program = di[Program]
    services = program.services

    assert services

    next_service: Service | None = None
    no_further_processing = ProcessedEvent(
        service=None,
        related_media_items=[],
    )
    items_to_submit: list[MediaItem] = []

    if existing_item and existing_item.last_state in [States.Paused, States.Failed]:
        return no_further_processing

    if content_item or (existing_item and existing_item.last_state == States.Requested):
        log_string = None

        if existing_item:
            log_string = existing_item.log_string
        elif content_item:
            log_string = content_item.log_string

        logger.debug(f"Submitting {log_string} to IndexerService")

        return ProcessedEvent(
            service=services.indexer,
            related_media_items=[content_item or existing_item],
        )

    elif existing_item and existing_item.last_state in [
        States.PartiallyCompleted,
        States.Ongoing,
    ]:
        if existing_item.type == "show":
            incomplete_seasons = [
                s
                for s in existing_item.seasons
                if s.last_state not in [States.Completed, States.Unreleased]
            ]

            for season in incomplete_seasons:
                processed_event = process_event(emitted_by, season, None)

                items_to_submit += processed_event.related_media_items
        elif existing_item.type == "season":
            incomplete_episodes = [
                e for e in existing_item.episodes if e.last_state != States.Completed
            ]

            for episode in incomplete_episodes:
                processed_event = process_event(emitted_by, episode, None)

                items_to_submit += processed_event.related_media_items

    elif existing_item and existing_item.last_state == States.Indexed:
        next_service = services.scraping

        if emitted_by != services.scraping and services.scraping.should_submit(
            existing_item
        ):
            items_to_submit = [existing_item]
        elif isinstance(existing_item, Show):
            items_to_submit = [
                s
                for s in existing_item.seasons
                if s.last_state
                in [States.Indexed, States.PartiallyCompleted, States.Unknown]
                and services.scraping.should_submit(s)
            ]
        elif isinstance(existing_item, Season):
            items_to_submit = [
                e
                for e in existing_item.episodes
                if e.last_state in [States.Indexed, States.Unknown]
                and services.scraping.should_submit(e)
            ]

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
    )
