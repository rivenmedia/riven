from coverage import Coverage
import inspect

from program.content import Overseerr, PlexWatchlist, Listrr, Mdblist
from program.indexers.trakt import TraktIndexer
from program.libaries import SymlinkLibrary
from program.realdebrid import Debrid
from program.scrapers import Scraping
from program.symlink import Symlinker
from program.updaters.plex import PlexUpdater

from program.types import ProcessedEvent, Service
from program.media import MediaItem, Season, Episode, Show, Movie, States
from utils.logger import logger


# Function to execute process_event and collect coverage data
def process_event_and_collect_coverage(
    existing_item: MediaItem | None, 
    emitted_by: Service, 
    item: MediaItem
) -> ProcessedEvent:
    file_path = inspect.getfile(process_event)
    cov = Coverage(source=[file_path])
    cov.start()

    # Call the process_event method
    updated_item, next_service, items_to_submit = process_event(
        existing_item, emitted_by, item
    )

    cov.stop()
    cov.save()

    # Analyze the coverage data for this execution
    # Here you would extract the lines executed within process_event
    # and log them along with the input and output
    cov_analysis = cov.analysis2(file_path)
    executed_lines = cov_analysis[1]  # List of executed lines

    return updated_item, next_service, items_to_submit


def process_event(existing_item: MediaItem | None, emitted_by: Service, item: MediaItem) -> ProcessedEvent:
    """Take the input event, process it, and output items to submit to a Service, and an item
    to update the container with."""
    next_service : Service = None
    updated_item = item
    no_further_processing: ProcessedEvent = (None, None, [])
    # we always want to get metadata for content items before we compare to the container. 
    # we can't just check if the show exists we have to check if it's complete
    source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary)
    if emitted_by in source_services or item.state == States.Unknown:
        next_service = TraktIndexer
        # seasons can't be indexed so we'll index and process the show instead
        if isinstance(item, Season):
            item = item.parent
            existing_item = existing_item.parent
        # if we already have a copy of this item check if we even need to index it
        if existing_item and not TraktIndexer.should_submit(existing_item):
            # ignore this item
            return no_further_processing
        # don't update the container until we've indexed the item
        return None, next_service, [item]
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
                item = existing_item
                
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
        elif Scraping.should_submit(item):
            items_to_submit = [item]
        else:
            items_to_submit = []
    # Only shows and seasons can be PartiallyCompleted.  This is also the last part of the state
    # processing that can can be at the show level
    elif item.state == States.PartiallyCompleted:
        next_service = Scraping
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons if s.state != States.Completed]
        elif isinstance(item, Season):
            items_to_submit = [e for e in item.episodes if e.state != States.Completed]
    # if we successfully scraped the item then send it to debrid
    elif item.state == States.Scraped:
        next_service = Debrid
        items_to_submit = [item]
    elif item.state == States.Downloaded:
        next_service = Symlinker
        if isinstance(item, Season):
            proposed_submissions = [e for e in item.episodes]
        elif isinstance(item, (Movie, Episode)):
            proposed_submissions = [item]
        items_to_submit = []
        for item in proposed_submissions:
            if not Symlinker.should_submit(item):
                logger.error("Item %s rejected by Symlinker, skipping", item.log_string)
            else:
                items_to_submit.append(item)
    elif item.state == States.Symlinked:
        next_service = PlexUpdater
        if isinstance(item, Show):
            items_to_submit = [s for s in item.seasons]
        elif isinstance(item, Season):
            items_to_submit = [e for e in item.episodes]
        else:
            items_to_submit = [item]
    elif item.state == States.Completed:
        return no_further_processing

    return updated_item, next_service, items_to_submit