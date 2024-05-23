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


def process_event(existing_item: MediaItem | None, emitted_by: Service, item: MediaItem) -> ProcessedEvent: # type: ignore
    """Process an event and return the updated item, next service and items to submit."""

    next_service: Service = None
    updated_item = item
    no_further_processing: ProcessedEvent = (None, None, [])  # type: ignore
    
    
    # we always want to get metadata for content items before we compare to the container.
    # we can't just check if the show exists we have to check if it's complete or if there are new episodes.

    # we always want to get metadata for content items before we compare to the container.
    # we can't just check if the show exists we have to check if it's complete or if there are new episodes.
    source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary)
    if emitted_by in source_services or item.state == States.Unknown:
        next_service = TraktIndexer
        if isinstance(item, Season):
            item = item.parent
            existing_item = existing_item.parent if existing_item else None
        if existing_item:
            should_submit = TraktIndexer.should_submit(existing_item)
            if not should_submit:
                return no_further_processing
        # logger.debug(f"Submitting item {item.log_string} to TraktIndexer")
        return None, next_service, [item]

    elif emitted_by == TraktIndexer or item.state == States.Indexed:
        # logger.debug(f"Item {item.log_string} is now Indexed")
        next_service = Scraping
        if existing_item:
            if not existing_item.indexed_at:
                if isinstance(item, (Show, Season)):
                    existing_item.fill_in_missing_children(item)
                existing_item.copy_other_media_attr(item)
                existing_item.indexed_at = item.indexed_at
                updated_item = item = existing_item
            if existing_item.state == States.Completed:
                return existing_item, None, []
        items_to_submit = []
        if item.scraped_times and isinstance(item, (Show, Season)):
            if isinstance(item, Show):
                items_to_submit = [s for s in item.seasons if s.state != States.Completed]
            elif isinstance(item, Season):
                items_to_submit = [e for e in item.episodes if e.state != States.Completed]
        elif Scraping.should_submit(item) and Scraping.is_released(item):
            items_to_submit = [item]

    elif item.state == States.PartiallyCompleted:
        # logger.debug(f"Item {item.log_string} is Partially Completed")
        next_service = Scraping
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons if s.state != States.Completed]
        elif isinstance(item, Season):
            items_to_submit = [e for e in item.episodes if e.state != States.Completed]

    elif item.state == States.Scraped:
        # logger.debug(f"Item {item.log_string} is Scraped")
        next_service = Debrid
        items_to_submit = [item]

    elif item.state == States.Downloaded:
        # logger.debug(f"Item {item.log_string} is Downloaded")
        next_service = Symlinker
        proposed_submissions = []
        if isinstance(item, Season):
            proposed_submissions = [e for e in item.episodes]
        elif isinstance(item, (Movie, Episode)):
            proposed_submissions = [item]
        items_to_submit = []
        for item in proposed_submissions:
            if Symlinker.check_file_existence(item):
                items_to_submit.append(item)
            elif not Symlinker.should_submit(item):
                logger.error("Item %s rejected by Symlinker, skipping", item.log_string)
            else:
                items_to_submit.append(item)

    elif item.state == States.Symlinked:
        # logger.debug(f"Item {item.log_string} is Symlinked")
        next_service = PlexUpdater
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons]
        elif isinstance(item, Season):
            items_to_submit = [e for e in item.episodes]
        else:
            items_to_submit = [item]

    elif item.state == States.Completed:
        # logger.debug(f"Item {item.log_string} is Completed")
        return no_further_processing

    return updated_item, next_service, items_to_submit
