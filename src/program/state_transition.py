from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.content.trakt import TraktContent
# from program.db.db_functions import _item_id_exists_in_db
from program.downloaders import Downloader
from program.indexers.trakt import TraktIndexer
from program.libraries import SymlinkLibrary
from program.media import MediaItem, Season, Show, States
from program.post_processing import PostProcessing, notify
from program.post_processing.subliminal import Subliminal
from program.scrapers import Scraping
from program.settings.manager import settings_manager
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
    if emitted_by in source_services or item.state in [States.Requested]:
        next_service = TraktIndexer
        # if _item_id_exists_in_db(item._id) and item.last_state == States.Completed:
        if item and isinstance(item._id, int) and item.last_state == States.Completed:
            logger.debug(f"Item {item.log_string} already exists in the database.")
            return no_further_processing
        if isinstance(item, Season):
            item = item.parent
            existing_item = existing_item.parent if existing_item else None
        if existing_item and not TraktIndexer.should_submit(existing_item):
            return no_further_processing
        return None, next_service, [item]

    elif item.last_state in [States.PartiallyCompleted, States.Ongoing]:
        if item.type == "show":
            for season in item.seasons:
                if season.last_state not in [States.Completed, States.Unreleased]:
                    _, _, sub_items = process_event(season, emitted_by, season)
                    items_to_submit += sub_items
        elif item.type == "season":
            for episode in item.episodes:
                if episode.last_state != States.Completed:
                    _, _, sub_items = process_event(episode, emitted_by, episode)
                    items_to_submit += sub_items

    elif item.last_state == States.Indexed:
        next_service = Scraping
        if existing_item:
            if not existing_item.indexed_at:
                if isinstance(item, (Show, Season)):
                    existing_item.fill_in_missing_children(item)
                existing_item.copy_other_media_attr(item)
                existing_item.indexed_at = item.indexed_at
                updated_item = item = existing_item
            if existing_item.last_state == States.Completed:
                return existing_item, None, []
            elif not emitted_by == Scraping and Scraping.can_we_scrape(existing_item):
                items_to_submit = [existing_item]
            elif item.type == "show":
                items_to_submit = [s for s in item.seasons if s.last_state != States.Completed and Scraping.can_we_scrape(s)]
            elif item.type == "season":
                items_to_submit = [e for e in item.episodes if e.last_state != States.Completed and Scraping.can_we_scrape(e)]

    elif item.last_state == States.Scraped:
        next_service = Downloader
        items_to_submit = [item]

    elif item.last_state == States.Downloaded:
        next_service = Symlinker
        items_to_submit = [item]

    elif item.last_state == States.Symlinked:
        next_service = Updater
        items_to_submit = [item]

    elif item.last_state == States.Completed:
        # If a user manually retries an item, lets not notify them again
        if emitted_by not in ["Manual", PostProcessing]:
            notify(item)
        # Avoid multiple post-processing runs
        if not emitted_by == PostProcessing:
            if settings_manager.settings.post_processing.subliminal.enabled:
                next_service = PostProcessing
                if item.type in ["movie", "episode"] and Subliminal.should_submit(item):
                    items_to_submit = [item]
                elif item.type == "show":
                    items_to_submit = [e for s in item.seasons for e in s.episodes if e.last_state == States.Completed and Subliminal.should_submit(e)]
                elif item.type == "season":
                    items_to_submit = [e for e in item.episodes if e.last_state == States.Completed and Subliminal.should_submit(e)]
                if not items_to_submit:
                    return no_further_processing
        else:
            return no_further_processing

    return updated_item, next_service, items_to_submit