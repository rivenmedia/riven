from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.content.trakt import TraktContent
from program.downloaders import Downloader
from program.indexers.trakt import TraktIndexer
from program.libraries import SymlinkLibrary
from program.media import Episode, MediaItem, Movie, Season, Show, States
from program.post_processing import PostProcessing
from program.post_processing.subliminal import Subliminal
from program.scrapers import Scraping
from program.symlink import Symlinker
from program.types import ProcessedEvent, Service
from program.updaters import Updater, OverseerrUpdater
from program.settings.manager import settings_manager


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
    
    elif item.last_overseerr_status is not None and item.last_overseerr_status != item.overseerr_status.name:
        next_service = OverseerrUpdater
        return None, next_service, [item]

    elif item.state in (States.Indexed, States.PartiallyCompleted):
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
            if item.type in ["movie", "episode"]:
                items_to_submit = [item] if Scraping.can_we_scrape(item) else []
            elif item.type == "show":
                if Scraping.can_we_scrape(item):
                    items_to_submit = [item]
                else:
                    for season in item.seasons:
                        if season.state in [States.Indexed, States.PartiallyCompleted] and Scraping.can_we_scrape(season):
                            items_to_submit.append(season)
                        elif season.state == States.Scraped:
                            next_service = Downloader
                            items_to_submit.append(season)
            elif item.type == "season":
                if Scraping.can_we_scrape(item):
                    items_to_submit = [item]
                else:
                    for episode in item.episodes:
                        if episode.state in [States.Indexed, States.PartiallyCompleted] and Scraping.can_we_scrape(episode):
                            items_to_submit.append(episode)
                        elif episode.state == States.Scraped:
                            next_service = Downloader
                            items_to_submit.append(episode)
                        elif episode.state == States.Downloaded:
                            next_service = Symlinker
                            items_to_submit.append(episode)

    elif item.state == States.Scraped:
        next_service = Downloader
        items_to_submit = []
        if item.type == "show":
            items_to_submit = [s for s in item.seasons if s.state == States.Downloaded]
        if item.type == "season":
            items_to_submit = [e for e in item.episodes if e.state == States.Downloaded]
        items_to_submit.append(item)

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
            items_to_submit.append(sub_item)

    elif item.state == States.Symlinked:
        next_service = Updater
        items_to_submit = [item]

    elif item.state == States.Completed:
            if settings_manager.settings.post_processing.subliminal.enabled:
                next_service = PostProcessing
                if item.type in ["movie", "episode"] and Subliminal.should_submit(item):
                    items_to_submit = [item]
                elif item.type == "show":
                    items_to_submit = [e for s in item.seasons for e in s.episodes if e.state == States.Completed and Subliminal.should_submit(e)]
                elif item.type == "season":
                    items_to_submit = [e for e in item.episodes if e.state == States.Completed and Subliminal.should_submit(e)]
                if not items_to_submit:
                    return no_further_processing
            else:
                return no_further_processing

    return updated_item, next_service, items_to_submit