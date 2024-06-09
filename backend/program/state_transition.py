from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.content.trakt import TraktContent
from program.downloaders.realdebrid import Debrid
from program.downloaders.torbox import TorBoxDownloader
from program.indexers.trakt import TraktIndexer
from program.libraries import PlexLibrary, SymlinkLibrary
from program.media import Episode, MediaItem, Movie, Season, Show, States
from program.scrapers import Scraping
from program.symlink import Symlinker
from program.types import ProcessedEvent, Service
from program.updaters.plex import PlexUpdater
from utils.logger import logger


def process_event(existing_item: MediaItem | None, emitted_by: Service, item: MediaItem) -> ProcessedEvent:
    """Process an event and return the updated item, next service and items to submit."""
    next_service: Service = None
    updated_item = item
    no_further_processing: ProcessedEvent = (None, None, [])
    items_to_submit = []

    source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary, TraktContent)  # PlexLibrary is a special case
    if emitted_by in source_services or item.state == States.Unknown:
        next_service = TraktIndexer
        if isinstance(item, Season):
            item = item.parent
            existing_item = existing_item.parent if existing_item else None
        if existing_item and not TraktIndexer.should_submit(existing_item):
            return no_further_processing
        return None, next_service, [item]

    elif emitted_by == TraktIndexer or item.state == States.Indexed:
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
        if Scraping.can_we_scrape(item):
            if isinstance(item, Movie):
                items_to_submit = [item]
            elif isinstance(item, Show):
                if item.scraped_times >= 4:
                    pass #Season handles this below.
                else:
                    items_to_submit = [item]
            elif isinstance(item, Season):
                if item.parent.scraped_times >=4:
                    if item.scraped_times >= 4:
                        pass
                    else:
                        items_to_submit = [item]
            else: 
                if( item.parent and item.parent.scraped_times > 4):
                    items_to_submit = [item]
                else:
                    if not item.parent:
                        items_to_submit = [item]
            
        else:
            items_to_submit = []

    elif item.state == States.PartiallyCompleted:
        next_service = Scraping
        if isinstance(item, Show):
            items_to_submit = [
                s for s in item.seasons 
                if s.state not in (States.Completed, States.PartiallyCompleted)
                and Scraping.can_we_scrape(s)
            ]
        elif isinstance(item, Season):
            items_to_submit = [
                e for e in item.episodes 
                if e.state == States.Indexed
                and Scraping.can_we_scrape(e)
            ]

    elif item.state == States.Scraped:
        next_service = Debrid or TorBoxDownloader
        items_to_submit = [item]

    elif item.state == States.Downloaded:
        next_service = Symlinker
        proposed_submissions = []
        if isinstance(item, Season):
            if all(e.file and e.folder for e in item.episodes if not e.symlinked):
                proposed_submissions = [item]
            else:
                proposed_submissions = [e for e in item.episodes if not e.symlinked and e.file and e.folder]
        elif isinstance(item, (Movie, Episode)):
            proposed_submissions = [item]
        elif isinstance(item, Show):
            proposed_submissions = [item]


        items_to_submit = []
        for sub_item in proposed_submissions:
            if Symlinker.should_submit(sub_item):
                items_to_submit.append(sub_item)
            else:
                logger.debug(f"{sub_item.log_string} not submitted to Symlinker because it is not eligible")

    elif item.state == States.Symlinked:
        next_service = PlexUpdater
        if isinstance(item, Show):
            items_to_submit = [item]
        elif isinstance(item, Season):
            items_to_submit = [item]
        else:
            items_to_submit = [item]

    elif item.state == States.Completed:
        return no_further_processing

    return updated_item, next_service, items_to_submit
