from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.content.trakt import TraktContent
from program.downloaders.realdebrid import Debrid
from program.downloaders.torbox import TorBoxDownloader
from program.indexers.trakt import TraktIndexer
from program.libraries import SymlinkLibrary
from program.media import Episode, MediaItem, Movie, Season, Show, States
from program.scrapers import Scraping
from program.symlink import Symlinker
from program.types import ProcessedEvent, Service
from program.updaters import Updater
from utils.logger import logger


def process_event(existing_item: MediaItem | None, emitted_by: Service, item: MediaItem) -> ProcessedEvent:
    """Process an event and return the updated item, next service and items to submit."""
    next_service: Service = None
    updated_item = item
    no_further_processing: ProcessedEvent = (None, None, [])
    items_to_submit = []

    source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary, TraktContent)
    if emitted_by in source_services or item.state in [States.Requested, States.Unknown]:
        next_service = TraktIndexer
        if isinstance(item, Season):
            item = item.parent
            existing_item = existing_item.parent if existing_item else None
        if existing_item and not TraktIndexer.should_submit(existing_item):
            return no_further_processing
        return None, next_service, [item]

    elif emitted_by == TraktIndexer or item.state == States.Indexed or item.state == States.PartiallyCompleted:
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
        items_to_submit = [item]

    elif item.state == States.Scraped:
        next_service = Debrid or TorBoxDownloader
        items_to_submit = [item]

    elif item.state == States.Downloaded:
        next_service = Symlinker
        proposed_submissions = []
        if isinstance(item, Show):
            all_found = all(
                all(e.file and e.folder for e in season.episodes if not e.symlinked)
                for season in item.seasons
            )
            if all_found:
                proposed_submissions = [item]
            else:
                proposed_submissions = [
                    e for season in item.seasons
                    for e in season.episodes
                    if not e.symlinked and e.file and e.folder
                ]
        elif isinstance(item, Season):
            if all(e.file and e.folder for e in item.episodes if not e.symlinked):
                proposed_submissions = [item]
            else:
                proposed_submissions = [e for e in item.episodes if not e.symlinked and e.file and e.folder]
        elif isinstance(item, (Movie, Episode)):
            proposed_submissions = [item]
        items_to_submit = []
        for sub_item in proposed_submissions:
            if Symlinker.should_submit(sub_item):
                items_to_submit.append(sub_item)
            else:
                logger.debug(f"{sub_item.log_string} not submitted to Symlinker because it is not eligible")

    elif item.state == States.Symlinked:
        next_service = Updater
        items_to_submit = [item]

    elif item.state == States.Completed:
        return no_further_processing

    return updated_item, next_service, items_to_submit