from loguru import logger

from program.media import MediaItem, States
from program.services.downloaders import Downloader
from program.services.indexers.trakt import TraktIndexer
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

    #TODO - Reindex non-released badly indexed items here
    if content_item or (existing_item is not None and existing_item.last_state == States.Requested):
        next_service = TraktIndexer
        logger.debug(f"Submitting {content_item.imdb_id if content_item else existing_item.log_string} to Trakt indexer")
        return next_service, [content_item or existing_item]

    elif existing_item is not None and existing_item.last_state in [States.PartiallyCompleted, States.Ongoing]:
        if existing_item.type == "show":
            for season in existing_item.seasons:
                if season.last_state not in [States.Completed, States.Unreleased]:
                    _, sub_items = process_event(emitted_by, season, None)
                    items_to_submit += sub_items
        elif existing_item.type == "season":
            for episode in existing_item.episodes:
                if episode.last_state != States.Completed:
                    _, sub_items = process_event(emitted_by, episode, None)
                    items_to_submit += sub_items

    elif existing_item is not None and existing_item.last_state == States.Indexed:
        next_service = Scraping
        if emitted_by != Scraping and Scraping.should_submit(existing_item):
            items_to_submit = [existing_item]
        elif existing_item.type == "show":
            items_to_submit = [s for s in existing_item.seasons if s.last_state in [States.Indexed, States.PartiallyCompleted, States.Unknown] and Scraping.should_submit(s)]
        elif existing_item.type == "season":
            items_to_submit = [e for e in existing_item.episodes if e.last_state in [States.Indexed, States.Unknown] and Scraping.should_submit(e)]

    elif existing_item is not None and existing_item.last_state == States.Scraped:
        next_service = Downloader
        items_to_submit = [existing_item]

    elif existing_item is not None and existing_item.last_state == States.Downloaded:
        next_service = Symlinker
        items_to_submit = [existing_item]

    elif existing_item is not None and existing_item.last_state == States.Symlinked:
        next_service = Updater
        items_to_submit = [existing_item]

    elif existing_item is not None and existing_item.last_state == States.Completed:
        # If a user manually retries an item, lets not notify them again
        if emitted_by not in ["RetryItem", PostProcessing]:
            notify(existing_item)
        # Avoid multiple post-processing runs
        if emitted_by != PostProcessing:
            if settings_manager.settings.post_processing.subliminal.enabled:
                next_service = PostProcessing
                if existing_item.type in ["movie", "episode"] and Subliminal.should_submit(existing_item):
                    items_to_submit = [existing_item]
                elif existing_item.type == "show":
                    items_to_submit = [e for s in existing_item.seasons for e in s.episodes if e.last_state == States.Completed and Subliminal.should_submit(e)]
                elif existing_item.type == "season":
                    items_to_submit = [e for e in existing_item.episodes if e.last_state == States.Completed and Subliminal.should_submit(e)]
                if not items_to_submit:
                    return no_further_processing
        else:
            return no_further_processing

    # if items_to_submit and next_service:
    #     for item in items_to_submit:
    #         logger.debug(f"Submitting {item.log_string} ({item.id}) to {next_service if isinstance(next_service, str) else next_service.__name__}")

    return next_service, items_to_submit
