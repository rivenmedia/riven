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


def process_event(existing_item: MediaItem | None, emitted_by: Service, item: MediaItem) -> ProcessedEvent:  # type: ignore
    """
    Process the input event, determine the next service to process the item, and return 
    items to update the container with.
    
    Args:
        existing_item (MediaItem | None): The existing item from the container.
        emitted_by (Service): The service that emitted the event.
        item (MediaItem): The media item to be processed.

    Returns:
        ProcessedEvent: A tuple containing the updated item, the next service to handle the item, and items to submit.
    """
    no_further_processing: ProcessedEvent = (None, None, [])  # type: ignore

    # Early return if item is already completed and has a title
    if item.state == States.Completed and item.get_top_title():
        return no_further_processing

    try:
        source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary)
        if emitted_by in source_services or item.state == States.Unknown:
            return handle_initial_states(existing_item, item)

        # Handle Indexed state where metadata needs to be merged
        if emitted_by == TraktIndexer or item.state == States.Indexed:
            return handle_indexed_state(existing_item, item)

        # Handle remaining states such as Scraped, Downloaded, Symlinked
        return handle_scraping_states(item)

    except Exception as e:
        logger.error(f"Error processing event for item {item}: {e}")
        return no_further_processing


def handle_initial_states(existing_item: MediaItem | None, item: MediaItem) -> ProcessedEvent:  # type: ignore
    """
    Handle initial states and return the next service to process the item if applicable.
    
    Args:
        existing_item (MediaItem | None): The existing item from the container.
        item (MediaItem): The media item to be processed.

    Returns:
        ProcessedEvent: A tuple containing the updated item, the next service to handle the item, and items to submit.
    """
    next_service = TraktIndexer
    # Seasons can't be indexed so we'll index and process the show instead
    if isinstance(item, Season):
        item = item.parent
        existing_item = existing_item.parent if existing_item else None
    # If we already have a copy of this item check if we even need to index it
    if existing_item and not TraktIndexer.should_submit(existing_item):
        return None, None, []
    return item, next_service, [item]


def handle_indexed_state(existing_item: MediaItem | None, item: MediaItem) -> ProcessedEvent:  # type: ignore
    """
    Handle the Indexed state and return the next service to process the item if applicable.
    
    Args:
        existing_item (MediaItem | None): The existing item from the container.
        item (MediaItem): The media item to be processed.

    Returns:
        ProcessedEvent: A tuple containing the updated item, the next service to handle the item, and items to submit.
    """
    next_service = Scraping

    if existing_item:
        if not existing_item.indexed_at:
            # Merge our fresh metadata item to make sure there aren't any missing seasons or episodes in our library copy
            if isinstance(item, (Show, Season)):
                existing_item.fill_in_missing_children(item)
            # Merge in the metadata in case it's missing (like on cold boot)
            existing_item.copy_other_media_attr(item)
            # Update the timestamp now that we have new metadata
            existing_item.indexed_at = item.indexed_at
            # Use the merged data for the rest of the state transition
            item = existing_item
        # If after filling in missing episodes we are still complete then skip
        if existing_item.state == States.Completed:
            return existing_item, None, []

    # We attempted to scrape it already and it failed, so try scraping each component
    if item.scraped_times and isinstance(item, (Show, Season)):
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons if s.state != States.Completed]
        elif isinstance(item, Season):
            if item.scraped_times == 0:
                items_to_submit = [item]
            else:
                items_to_submit = [
                    e for e in item.episodes if e.state != States.Completed
                ]
    elif Scraping.should_submit(item):
        items_to_submit = [item]
    else:
        items_to_submit = []

    return item, next_service, items_to_submit


def handle_scraping_states(item: MediaItem) -> ProcessedEvent:  # type: ignore
    """
    Handle the states related to scraping, downloading, and symlinking.
    
    Args:
        item (MediaItem): The media item to be processed.

    Returns:
        ProcessedEvent: A tuple containing the updated item, the next service to handle the item, and items to submit.
    """
    if item.state == States.Completed:
        return None, None, []

    next_service = None
    items_to_submit = []

    if item.state == States.PartiallyCompleted:
        next_service = Scraping
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons if s.state != States.Completed]
        elif isinstance(item, Season):
            items_to_submit = [e for e in item.episodes if e.state != States.Completed]
    elif item.state == States.Scraped:
        next_service = Debrid
        items_to_submit = [item]
    elif item.state == States.Downloaded:
        next_service = Symlinker
        items_to_submit = prepare_symlink_items(item)
    elif item.state == States.Symlinked:
        next_service = PlexUpdater
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons]
        elif isinstance(item, Season):
            items_to_submit = [e for e in item.episodes]
        else:
            items_to_submit = [item]

    return item, next_service, items_to_submit


def prepare_symlink_items(item: MediaItem) -> list[MediaItem]:
    """
    Prepare items for symlinking.
    
    Args:
        item (MediaItem): The media item to be symlinked.

    Returns:
        list[MediaItem]: A list of items to be symlinked.
    """
    proposed_submissions = []
    if isinstance(item, Season):
        proposed_submissions = [e for e in item.episodes]
    elif isinstance(item, (Movie, Episode)):
        proposed_submissions = [item]

    items_to_submit = []
    for item in proposed_submissions:
        if Symlinker.should_submit(item):
            items_to_submit.append(item)

    return items_to_submit
