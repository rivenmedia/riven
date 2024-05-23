import time
from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.indexers.trakt import TraktIndexer
from program.libaries import SymlinkLibrary
from program.media import Episode, MediaItem, Movie, Season, Show, States
from program.realdebrid import Debrid
from program.scrapers import Scraping
from program.symlink import Symlinker
from program.types import ProcessedEvent, Service
from program.updaters.plex import PlexUpdater


def process_event(existing_item: MediaItem | None, emitted_by: Service, item: MediaItem) -> ProcessedEvent:  # type: ignore
    """Take the input event, process it, and output items to submit to a Service, and an item
    to update the container with."""
    next_service: Service = None
    updated_item = item
    no_further_processing: ProcessedEvent = (None, None, [])  # type: ignore
    
    # we always want to get metadata for content items before we compare to the container.
    # we can't just check if the show exists we have to check if it's complete or if there are new episodes.
    source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary)

    # Handle Requested and Unknown states
    if emitted_by in source_services or item.state == States.Unknown:
        next_service = TraktIndexer
        # seasons can't be indexed so we'll index and process the show instead
        if isinstance(item, Season):
            item = item.parent
            existing_item = existing_item.parent if existing_item else None
            # if we already have a copy of this item check if we even need to index it
        if existing_item and not TraktIndexer.should_submit(existing_item):
            # ignore this item
            return no_further_processing
        # don't update the container until we've indexed the item
        return None, next_service, [item]

    # Handle Indexed state
    elif emitted_by == TraktIndexer or item.state == States.Indexed:
        next_service = Scraping
        if existing_item:
            if not existing_item.indexed_at:
                # merge our fresh metadata item to make sure there aren't any
                # missing seasons or episodes in our library copy
                if isinstance(item, (Show, Season)):
                    existing_item.fill_in_missing_children(item)
                # merge in the metadata in case its missing (like on cold boot)
                existing_item.copy_other_media_attr(item)
                # update the timestamp now that we have new metadata
                existing_item.indexed_at = item.indexed_at
                # use the merged data for the rest of the state transition
                updated_item = item = existing_item
            # if after filling in missing episodes we are still complete then skip
            if existing_item.state == States.Completed:
                # make sure to update with the (potentially) newly merged item
                return existing_item, None, []
        # we attempted to scrape it already and it failed, so try scraping each component
        if item.scraped_times and isinstance(item, (Show, Season)):
            if isinstance(item, Show):
                items_to_submit = [s for s in item.seasons if s.state != States.Completed]
            elif isinstance(item, Season):
                items_to_submit = [e for e in item.episodes if e.state != States.Completed]

        # We should also make sure that the item is even released before we try to scrape it
        elif Scraping.should_submit(item) and Scraping.is_released(item):
            items_to_submit = [item]
        else:
            items_to_submit = []

    # Handle Scraped state
    elif item.state == States.PartiallyCompleted:
        # Only shows and seasons can be PartiallyCompleted.  This is also the last part of the state
        # processing that can can be at the show level
        next_service = Scraping
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons if s.state != States.Completed]
        elif isinstance(item, Season):
            items_to_submit = [e for e in item.episodes if e.state != States.Completed]

    # Handle Scraped state
    elif item.state == States.Scraped:
        next_service = Debrid
        items_to_submit = [item]

    # Handle Downloaded state
    elif item.state == States.Downloaded:
        next_service = Symlinker
        proposed_submissions = []
        if isinstance(item, Season):
            proposed_submissions = [e for e in item.episodes]
        elif isinstance(item, (Movie, Episode)):
            proposed_submissions = [item]
        items_to_submit = []
        for item in proposed_submissions:
            if not Symlinker.should_submit(item):
                pass
            else:
                items_to_submit.append(item)

    # Handle Symlinked state
    elif item.state == States.Symlinked:
        next_service = PlexUpdater
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons]
        elif isinstance(item, Season):
            items_to_submit = [e for e in item.episodes]
        else:
            items_to_submit = [item]

    # Handle Completed state
    elif item.state == States.Completed:
        return no_further_processing

    return updated_item, next_service, items_to_submit
