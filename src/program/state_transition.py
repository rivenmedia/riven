from loguru import logger

from program.media import MediaItem, States
from program.services.downloaders import Downloader
from program.services.indexers import IndexerService
from program.services.post_processing import PostProcessing, notify
from program.services.post_processing.subliminal import Subliminal
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.settings.manager import settings_manager
from program.symlink import Symlinker
from program.types import ProcessedEvent, Service


def process_event(emitted_by: Service, existing_item: MediaItem | None = None, content_item: MediaItem | None = None) -> ProcessedEvent:
    """Process an event and return the updated item, next service and items to submit."""
    next_service: Service = None
    no_further_processing: ProcessedEvent = (None, [])
    items_to_submit = []

    if existing_item and existing_item.last_state in [States.Paused, States.Failed]:
        # logger.debug(f"Skipping {existing_item.log_string}: Item is {existing_item.last_state.name}. Manual intervention required.")
        return no_further_processing

    if content_item or (existing_item is not None and existing_item.last_state == States.Requested):
        next_service = IndexerService
        log_string = None
        if existing_item:
            log_string = existing_item.log_string
        elif content_item:
            if content_item.type == "movie":
                log_string = f"TMDB {content_item.tmdb_id or content_item.imdb_id}"
            elif content_item.type == "show":
                log_string = f"TVDB {content_item.tvdb_id or content_item.imdb_id}"
            elif content_item.type == "season":
                log_string = f"TVDB {content_item.tvdb_id or content_item.imdb_id}"
            elif content_item.type == "episode":
                log_string = f"TVDB {content_item.tvdb_id or content_item.imdb_id}"
        logger.debug(f"Submitting {log_string} to IndexerService")
        return next_service, [content_item or existing_item]

    elif existing_item is not None and existing_item.last_state in [States.PartiallyCompleted, States.Ongoing]:
        if existing_item.type == "show":
            incomplete_seasons = [s for s in existing_item.seasons if s.last_state not in [States.Completed, States.Unreleased]]
            logger.debug(f"Found {len(incomplete_seasons)} incomplete seasons to process for {existing_item.id}")
            for season in incomplete_seasons:
                _, sub_items = process_event(emitted_by, season, None)
                items_to_submit += sub_items
        elif existing_item.type == "season":
            incomplete_episodes = [e for e in existing_item.episodes if e.last_state != States.Completed]
            logger.debug(f"Found {len(incomplete_episodes)} incomplete episodes to process for {existing_item.id}")
            for episode in incomplete_episodes:
                _, sub_items = process_event(emitted_by, episode, None)
                items_to_submit += sub_items

    elif existing_item is not None and existing_item.last_state == States.Indexed:
        next_service = Scraping
        if emitted_by != Scraping and Scraping.should_submit(existing_item):
            items_to_submit = [existing_item]
            logger.debug(f"Next service: {next_service.__name__} for {existing_item.id}")
        elif existing_item.type == "show":
            items_to_submit = [s for s in existing_item.seasons if s.last_state in [States.Indexed, States.PartiallyCompleted, States.Unknown] and Scraping.should_submit(s)]
            if items_to_submit:
                logger.debug(f"Next service: {next_service.__name__} for {len(items_to_submit)} seasons from {existing_item.id}")
        elif existing_item.type == "season":
            items_to_submit = [e for e in existing_item.episodes if e.last_state in [States.Indexed, States.Unknown] and Scraping.should_submit(e)]
            if items_to_submit:
                logger.debug(f"Next service: {next_service.__name__} for {len(items_to_submit)} episodes from {existing_item.id}")

    elif existing_item is not None and existing_item.last_state == States.Scraped:
        next_service = Downloader
        items_to_submit = [existing_item]
        logger.debug(f"Next service: {next_service.__name__} for {existing_item.id}")

    elif existing_item is not None and existing_item.last_state == States.Downloaded:
        next_service = Symlinker
        items_to_submit = [existing_item]
        logger.debug(f"Next service: {next_service.__name__} for {existing_item.id}")

    elif existing_item is not None and existing_item.last_state == States.Symlinked:
        next_service = Updater
        items_to_submit = [existing_item]
        logger.debug(f"Next service: {next_service.__name__} for {existing_item.id}")

    elif existing_item is not None and existing_item.last_state == States.Completed:
        logger.debug(f"Item completed: {existing_item.id}")
        # If a user manually retries an item, lets not notify them again
        if emitted_by not in ["RetryItem", PostProcessing]:
            notify(existing_item)
        # Avoid multiple post-processing runs
        if emitted_by != PostProcessing:
            if settings_manager.settings.post_processing.subliminal.enabled:
                next_service = PostProcessing
                if existing_item.type in ["movie", "episode"] and Subliminal.should_submit(existing_item):
                    items_to_submit = [existing_item]
                    logger.debug(f"Next service: {next_service.__name__} for {existing_item.id}")
                elif existing_item.type == "show":
                    items_to_submit = [e for s in existing_item.seasons for e in s.episodes if e.last_state == States.Completed and Subliminal.should_submit(e)]
                    if items_to_submit:
                        logger.debug(f"Next service: {next_service.__name__} for {len(items_to_submit)} episodes from {existing_item.id}")
                elif existing_item.type == "season":
                    items_to_submit = [e for e in existing_item.episodes if e.last_state == States.Completed and Subliminal.should_submit(e)]
                    if items_to_submit:
                        logger.debug(f"Next service: {next_service.__name__} for {len(items_to_submit)} episodes from {existing_item.id}")
                if not items_to_submit:
                    logger.debug(f"No post-processing needed for {existing_item.id}")
                    return no_further_processing
        else:
            logger.debug(f"Post-processing already completed for {existing_item.id}")
            return no_further_processing

    # Log the final result of state transition
    if not next_service and not items_to_submit:
        if existing_item:
            logger.debug(f"No further processing needed for {existing_item.id} (State: {existing_item.last_state.name})")
        else:
            logger.debug(f"No further processing needed")
    elif items_to_submit:
        service_name = next_service.__name__ if next_service else "StateTransition"
        logger.debug(f"State transition complete: {len(items_to_submit)} items queued for {service_name}")

    return next_service, items_to_submit
