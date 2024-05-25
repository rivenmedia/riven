from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.indexers.trakt import TraktIndexer
from program.libaries import SymlinkLibrary
from program.media import Episode, MediaItem, Movie, Season, Show, States
from program.realdebrid import Debrid
from program.scrapers import Scraping
from program.symlink import Symlinker
from program.types import ProcessedEvent, Service
from program.updaters.plex import PlexUpdater


def process_event(existing_item: MediaItem | None, emitted_by: Service, item: MediaItem) -> ProcessedEvent: # type: ignore
    """Process an event and return the updated item, next service and items to submit."""
    next_service: Service = None
    updated_item = item
    no_further_processing: ProcessedEvent = (None, None, [])  # type: ignore
    items_to_submit = set()

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
        if Scraping.can_we_scrape(item):
            if isinstance(item, Show):
                items_to_submit.update(s for s in item.seasons if s.state != States.Completed)
            elif isinstance(item, Season):
                if item.scraped_times >= 3:
                    items_to_submit.add(item)
                else:
                    items_to_submit.update(e for e in item.episodes if e.state != States.Completed)
            elif isinstance(item, (Movie, Episode)):
                items_to_submit.add(item)

    elif item.state == States.PartiallyCompleted:
        next_service = Scraping
        if isinstance(item, Show):
            items_to_submit.update(s for s in item.seasons if s.state != States.Completed)
        elif isinstance(item, Season):
            items_to_submit.update(e for e in item.episodes if e.state != States.Completed)

    elif item.state == States.Scraped and item.streams and not isinstance(item, Show):
        next_service = Debrid
        items_to_submit.add(item)

    elif item.state == States.Downloaded:
        next_service = Symlinker
        proposed_submissions = []
        if isinstance(item, Season):
            proposed_submissions = item.episodes
        elif isinstance(item, (Movie, Episode)):
            proposed_submissions = [item]
        items_to_submit.update(i for i in proposed_submissions if Symlinker.check_file_existence(i) or Symlinker.should_submit(i))

    elif item.state == States.Symlinked:
        next_service = PlexUpdater
        if isinstance(item, Show):
            items_to_submit.update(item.seasons)
        elif isinstance(item, Season):
            items_to_submit.update(item.episodes)
        else:
            items_to_submit.add(item)

    elif item.state == States.Completed:
        return no_further_processing

    return updated_item, next_service, list(items_to_submit)
