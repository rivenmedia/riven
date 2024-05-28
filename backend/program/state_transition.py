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
    items_to_submit = []

    source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary)
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
        if isinstance(item, Movie):
            if Scraping.should_submit(item) and item.is_released:
                items_to_submit = [item]
        elif isinstance(item, Show):
            if Scraping.should_submit(item) and item.is_released:
                items_to_submit = [s for s in item.seasons if s.state not in (States.Completed, States.Downloaded, States.Scraped)
                                   and s.scraped_times < 3]
        elif isinstance(item, Season):
            if item.scraped_times < 3:
                items_to_submit = []
            else:
                items_to_submit = [e for e in item.episodes if e.state not in (States.Completed, States.Downloaded, States.Scraped)]
        elif isinstance(item, Episode):
            if item.state != States.Unknown:
                items_to_submit = [item]

    elif item.state == States.PartiallyCompleted:
        next_service = Scraping
        if isinstance(item, Show):
            if Scraping.should_submit(item) and item.is_released:
                items_to_submit = [s for s in item.seasons if s.state == States.PartiallyCompleted
                                       and s.scraped_times < 3 and not (s.file or s.folder)]
        elif isinstance(item, Season):
            if item.scraped_times < 3:
                items_to_submit = []
            else:
                if Scraping.should_submit(item) and item.is_released:
                    items_to_submit = [
                        e for e in item.episodes if e.state not in (States.Completed, States.Downloaded, States.Scraped)
                        and e.parent.scraped_times >= 3 and not (e.file or e.folder)
                    ]

    elif item.state == States.Scraped and len(item.streams) > 0 and not isinstance(item, Show):
        next_service = Debrid
        items_to_submit = [item]

    elif item.state == States.Downloaded and isinstance(item, (Movie, Season, Episode)):
        next_service = Symlinker
        proposed_submissions = []
        if isinstance(item, Season):
            proposed_submissions = item.episodes
        elif isinstance(item, (Movie, Episode)):
            proposed_submissions = [item]
        items_to_submit = [i for i in proposed_submissions if Symlinker.should_submit(i)]

    elif item.state == States.Symlinked:
        next_service = PlexUpdater
        if isinstance(item, Show):
            items_to_submit = item.seasons
        elif isinstance(item, Season):
            items_to_submit = item.episodes
        else:
            items_to_submit = [item]

    elif item.state == States.Completed:
        return no_further_processing

    return updated_item, next_service, items_to_submit
