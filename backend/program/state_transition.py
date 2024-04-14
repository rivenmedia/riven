from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.indexers.trakt import TraktIndexer
from program.libaries import SymlinkLibrary
from program.media import Episode, MediaItem, Movie, Season, Show, States
from program.realdebrid import Debrid
from program.scrapers import Scraping
from program.symlink import Symlinker
from program.types import ProcessedEvent, Service
from program.updaters.plex import PlexUpdater
from utils.logger import logger


def process_event(existing_item: MediaItem | None, emitted_by: Service, item: MediaItem) -> ProcessedEvent: # type: ignore  # noqa: PLR0912, C901
    """
    Process the state transition of a media item based on the service that emitted the event.

    Args:
        existing_item (MediaItem | None): The current state of the media item in the system, if any.
        emitted_by (Service): The service that emitted the current event.
        item (MediaItem): The media item that is being processed.

    Returns:
        ProcessedEvent: A tuple containing the updated item, the next service to handle this item, and any items to submit.
    """
    # Initialize default values for the return structure
    next_service: Service = None
    updated_item = item
    no_further_processing: ProcessedEvent = (None, None, []) # type: ignore
    items_to_submit = []

    # Define source services that trigger metadata fetching
    source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary)
    
    # Processing logic for items from source services or unknown state
    if emitted_by in source_services or item.state == States.Unknown:
        # found new item
        logger.info("Found new item: %s", item.log_string)
        next_service = TraktIndexer
        if isinstance(item, Season):
            logger.debug("Item '%s' is a season, converting to show for processing.", item.log_string)
            item = item.parent
            existing_item = existing_item.parent if existing_item else None
        if existing_item and not TraktIndexer.should_submit(existing_item):
            return no_further_processing
        return None, next_service, [item]

    # Logic for items that have been indexed
    elif emitted_by == TraktIndexer or item.state == States.Indexed:
        logger.debug("Item has been indexed, determining further actions: %s", item.log_string)
        next_service = Scraping
        if existing_item:
            # Merge metadata and update timestamps
            if not existing_item.indexed_at:
                logger.debug("Merging metadata for item: %s", item.log_string)
                if isinstance(item, (Show, Season)):
                    existing_item.fill_in_missing_children(item)
                existing_item.copy_other_media_attr(item)
                existing_item.indexed_at = item.indexed_at
                updated_item = item = existing_item
            if existing_item.state == States.Completed:
                logger.debug("Item state is completed, no further processing required: %s", item.log_string)
                return updated_item, None, []
        items_to_submit = _determine_items_to_submit_for_scraping(item)

    # Logic for partially completed items
    elif item.state == States.PartiallyCompleted:
        logger.debug("Item is partially completed, determining further actions: %s", item.log_string)
        next_service = Scraping
        items_to_submit = _filter_incomplete_media(item)

    # Logic for scraped items ready for download
    elif item.state == States.Scraped:
        next_service = Debrid
        items_to_submit = [item]

    # Logic for downloaded items ready for symlink creation
    elif item.state == States.Downloaded:
        next_service = Symlinker
        proposed_submissions = _get_proposed_submissions(item)
        items_to_submit = _filter_valid_symlinks(proposed_submissions)

    # Update Plex with symlinked items
    elif item.state == States.Symlinked:
        logger.debug("Item symlinked, updating Plex for item: %s", item.log_string)
        next_service = PlexUpdater
        items_to_submit = _expand_media_items(item)

    # Completed items require no further action
    elif item.state == States.Completed:
        logger.info("Item Completed Processing: %s", item.log_string)
        return no_further_processing

    return updated_item, next_service, items_to_submit


# Helper functions

def _determine_items_to_submit_for_scraping(item):
    """
    Determine which items should be submitted for scraping based on their state and previous attempts.

    Args:
        item (MediaItem): The media item being considered for scraping.

    Returns:
        List[MediaItem]: A list of media items that need scraping.
    """
    logger.debug("Determining items to submit for scraping for: %s", item.log_string)
    if item.scraped_times and isinstance(item, (Show, Season)):
        if isinstance(item, Show):
            return [s for s in item.seasons if s.state != States.Completed]
        elif isinstance(item, Season):
            return [e for e in item.episodes if e.state != States.Completed]
    return [item] if Scraping.should_submit(item) else []


def _filter_incomplete_media(item):
    if isinstance(item, Show):
        return [s for s in item.seasons if s.state != States.Completed]
    elif isinstance(item, Season):
        return [e for e in item.episodes if e.state != States.Completed]
    return []

def _get_proposed_submissions(item):
    if isinstance(item, Season):
        return [e for e in item.episodes]
    elif isinstance(item, (Movie, Episode)):
        return [item]
    return []

def _filter_valid_symlinks(proposed_submissions):
    return [item for item in proposed_submissions if Symlinker.should_submit(item)]

def _expand_media_items(item):
    if isinstance(item, Show):
        return [s for s in item.seasons]
    elif isinstance(item, Season):
        return [e for e in item.episodes]
    return [item]
