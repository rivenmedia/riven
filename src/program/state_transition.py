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
    """Optimized event processing with reduced redundant operations and better filtering."""
    next_service: Service = None
    no_further_processing: ProcessedEvent = (None, [])
    items_to_submit = []

    # Early exit for blocked states
    if existing_item and existing_item.last_state in [States.Paused, States.Failed]:
        return no_further_processing

    # Handle new content or requested items
    if content_item or (existing_item is not None and existing_item.last_state == States.Requested):
        next_service = TraktIndexer
        target_item = content_item or existing_item
        logger.debug(f"Submitting {target_item.imdb_id if hasattr(target_item, 'imdb_id') and target_item.imdb_id else target_item.log_string} to Trakt indexer")
        return next_service, [target_item]

    elif existing_item is not None and existing_item.last_state in [States.PartiallyCompleted, States.Ongoing]:
        # Optimized nested processing with batch operations
        items_to_submit = _get_incomplete_children(existing_item, emitted_by)

    elif existing_item is not None and existing_item.last_state == States.Indexed:
        next_service = Scraping
        items_to_submit = _get_scrapeable_items(existing_item, emitted_by)

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
        # Handle notifications and post-processing efficiently
        return _handle_completed_item(existing_item, emitted_by)

    # if items_to_submit and next_service:
    #     for item in items_to_submit:
    #         logger.debug(f"Submitting {item.log_string} ({item.id}) to {next_service if isinstance(next_service, str) else next_service.__name__}")

    return next_service, items_to_submit


def _get_incomplete_children(item: MediaItem, emitted_by: Service) -> list[MediaItem]:
    """
    Efficiently get incomplete child items for processing.

    Args:
        item: Parent MediaItem (show or season)
        emitted_by: Service that emitted the event

    Returns:
        List of child items that need processing
    """
    items_to_submit = []

    if item.type == "show":
        # Batch process seasons - avoid recursive calls
        incomplete_seasons = [
            season for season in item.seasons
            if season.last_state not in [States.Completed, States.Unreleased]
        ]

        for season in incomplete_seasons:
            if season.last_state in [States.PartiallyCompleted, States.Ongoing]:
                # Get incomplete episodes directly
                incomplete_episodes = [
                    episode for episode in season.episodes
                    if episode.last_state != States.Completed
                ]
                items_to_submit.extend(incomplete_episodes)
            else:
                items_to_submit.append(season)

    elif item.type == "season":
        # Get incomplete episodes directly
        incomplete_episodes = [
            episode for episode in item.episodes
            if episode.last_state != States.Completed
        ]
        items_to_submit.extend(incomplete_episodes)

    return items_to_submit


def _get_scrapeable_items(item: MediaItem, emitted_by: Service) -> list[MediaItem]:
    """
    Efficiently get items that need scraping.

    Args:
        item: MediaItem to check for scraping
        emitted_by: Service that emitted the event

    Returns:
        List of items that need scraping
    """
    if emitted_by != Scraping and Scraping.should_submit(item):
        return [item]

    items_to_submit = []

    if item.type == "show":
        # Use list comprehension for better performance
        scrapeable_states = [States.Indexed, States.PartiallyCompleted, States.Unknown]
        items_to_submit = [
            season for season in item.seasons
            if season.last_state in scrapeable_states and Scraping.should_submit(season)
        ]
    elif item.type == "season":
        scrapeable_states = [States.Indexed, States.Unknown]
        items_to_submit = [
            episode for episode in item.episodes
            if episode.last_state in scrapeable_states and Scraping.should_submit(episode)
        ]

    return items_to_submit


def _handle_completed_item(item: MediaItem, emitted_by: Service) -> ProcessedEvent:
    """
    Handle completed items with optimized notification and post-processing.

    Args:
        item: Completed MediaItem
        emitted_by: Service that emitted the event

    Returns:
        ProcessedEvent tuple
    """
    no_further_processing = (None, [])

    # Handle notifications
    if emitted_by not in ["RetryItem", PostProcessing]:
        notify(item)

    # Handle post-processing
    if emitted_by == PostProcessing:
        return no_further_processing

    if not settings_manager.settings.post_processing.subliminal.enabled:
        return no_further_processing

    items_to_submit = []

    if item.type in ["movie", "episode"] and Subliminal.should_submit(item):
        items_to_submit = [item]
    elif item.type == "show":
        # Optimized nested comprehension
        items_to_submit = [
            episode for season in item.seasons
            for episode in season.episodes
            if episode.last_state == States.Completed and Subliminal.should_submit(episode)
        ]
    elif item.type == "season":
        items_to_submit = [
            episode for episode in item.episodes
            if episode.last_state == States.Completed and Subliminal.should_submit(episode)
        ]

    if not items_to_submit:
        return no_further_processing

    return PostProcessing, items_to_submit
