from loguru import logger

from program.media import MediaItem, States
from program.services.downloaders import Downloader
from program.services.filesystem import FilesystemService
from program.services.indexers import IndexerService
from program.services.post_processing import PostProcessing
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.types import ProcessedEvent, Service


def process_event(
    emitted_by: Service,
    existing_item: MediaItem | None = None,
    content_item: MediaItem | None = None,
) -> ProcessedEvent:
    """Process an event and return the updated item, next service and items to submit."""
    next_service: Service = None
    no_further_processing: ProcessedEvent = (None, [])
    items_to_submit = []

    if existing_item and existing_item.last_state in [States.Paused, States.Failed]:
        return no_further_processing

    if content_item or (
        existing_item is not None and existing_item.last_state == States.Requested
    ):
        next_service = IndexerService
        log_string = None
        if existing_item:
            log_string = existing_item.log_string
        elif content_item:
            log_string = content_item.log_string
        logger.debug(f"Submitting {log_string} to IndexerService")
        return next_service, [content_item or existing_item]

    elif existing_item is not None and existing_item.last_state in [
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
                _, sub_items = process_event(emitted_by, season, None)
                items_to_submit += sub_items
        elif existing_item.type == "season":
            incomplete_episodes = [
                e for e in existing_item.episodes if e.last_state != States.Completed
            ]
            for episode in incomplete_episodes:
                _, sub_items = process_event(emitted_by, episode, None)
                items_to_submit += sub_items

    elif existing_item is not None and existing_item.last_state == States.Indexed:
        next_service = Scraping
        if emitted_by != Scraping and Scraping.should_submit(existing_item):
            items_to_submit = [existing_item]
        elif existing_item.type == "show":
            items_to_submit = [
                s
                for s in existing_item.seasons
                if s.last_state
                in [States.Indexed, States.PartiallyCompleted, States.Unknown]
                and Scraping.should_submit(s)
            ]
        elif existing_item.type == "season":
            items_to_submit = [
                e
                for e in existing_item.episodes
                if e.last_state in [States.Indexed, States.Unknown]
                and Scraping.should_submit(e)
            ]

    elif existing_item is not None and existing_item.last_state == States.Scraped:
        next_service = Downloader
        items_to_submit = [existing_item]

    elif existing_item is not None and existing_item.last_state == States.Downloaded:
        next_service = FilesystemService
        items_to_submit = [existing_item]

    elif existing_item is not None and existing_item.last_state == States.Symlinked:
        next_service = Updater
        items_to_submit = [existing_item]

    elif existing_item is not None and existing_item.last_state == States.Completed:
        # Avoid multiple post-processing runs
        if emitted_by != PostProcessing:
            next_service = PostProcessing
            items_to_submit = [existing_item]
        else:
            return no_further_processing

    if items_to_submit:
        service_name = next_service.__name__ if next_service else "StateTransition"
        logger.debug(
            f"State transition complete: {len(items_to_submit)} items queued for {service_name}"
        )

    return next_service, items_to_submit
