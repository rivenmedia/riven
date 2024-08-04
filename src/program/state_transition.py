from program.content import Listrr, Mdblist, Overseerr, PlexWatchlist
from program.content.trakt import TraktContent
from program.downloaders import Downloader
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
    no_further_processing: ProcessedEvent = (None, None, [])
    items_to_submit = []

    source_services = (Overseerr, PlexWatchlist, Listrr, Mdblist, SymlinkLibrary, TraktContent, "RetryLibrary", "Manual")
    if not existing_item and emitted_by in source_services or existing_item and existing_item.state in [States.Requested, States.Unknown]:
        next_service = TraktIndexer
        if isinstance(item, Season):
            item = item.parent
            existing_item = existing_item.parent if existing_item else None
        if existing_item and not TraktIndexer.should_submit(existing_item):
            return no_further_processing
        return None, next_service, [item]

    if existing_item:
        if existing_item.state in (States.Indexed, States.PartiallyCompleted):
            next_service = Scraping
            if existing_item:
                if not existing_item.indexed_at:
                    if isinstance(item, (Show, Season)):
                        existing_item.fill_in_missing_children(item)
                    existing_item.copy_other_media_attr(item)
                    existing_item.indexed_at = item.indexed_at
                if existing_item.state == States.Completed:
                    return existing_item, None, []
                if existing_item.type in ("movie", "episode"):
                    items_to_submit = [existing_item] if Scraping.can_we_scrape(existing_item) else []
                elif existing_item.type == "show":
                    if Scraping.can_we_scrape(existing_item):
                        items_to_submit = [existing_item]
                    else:
                        for season in existing_item.seasons:
                            if season.state in (States.Indexed, States.PartiallyCompleted) and Scraping.can_we_scrape(season):
                                items_to_submit.append(season)
                            elif season.state == States.Scraped:
                                next_service = Downloader
                                items_to_submit.append(season)
                elif existing_item.type == "season":
                    if Scraping.can_we_scrape(existing_item):
                        items_to_submit = [existing_item]
                    else:
                        for episode in existing_item.episodes:
                            if episode.state == States.Indexed and Scraping.can_we_scrape(episode):
                                items_to_submit.append(episode)
                            elif episode.state == States.Scraped:
                                next_service = Downloader
                                items_to_submit.append(episode)
                            elif episode.state == States.Downloaded:
                                next_service = Symlinker
                                items_to_submit.append(episode)

        elif existing_item.state == States.Scraped:
            next_service = Downloader
            items_to_submit = []
            if existing_item.type in ["movie", "episode"]:
                items_to_submit.append(existing_item)
            elif existing_item.type == "show":
                seasons_to_promote = [s for s in existing_item.seasons if s.state == States.Downloaded]
                episodes_to_promote = [e for s in existing_item.seasons if s.state != States.Completed for e in s.episodes if e.state == States.Downloaded]
                if seasons_to_promote:
                    next_service = Symlinker
                    items_to_submit = seasons_to_promote
                items_to_submit.append(existing_item)
            elif existing_item.type == "season":
                episodes_to_promote = [e for e in existing_item.episodes if e.state == States.Downloaded]
                if episodes_to_promote:
                    next_service = Symlinker
                    items_to_submit = episodes_to_promote
                items_to_submit.append(existing_item)


        elif existing_item.state == States.Downloaded :
            next_service = Symlinker
            proposed_submissions = []
            if isinstance(existing_item, Show):
                all_found = all(
                    all(e.file and e.folder for e in season.episodes if not e.symlinked)
                    for season in existing_item.seasons
                )
                if all_found:
                    proposed_submissions = [existing_item]
                else:
                    proposed_submissions = [
                        e for season in existing_item.seasons
                        for e in season.episodes
                        if not e.symlinked and e.file and e.folder
                    ]
            elif isinstance(existing_item, Season):
                if all(e.file and e.folder for e in item.episodes if not e.symlinked):
                    proposed_submissions = [existing_item]
                else:
                    proposed_submissions = [e for e in existing_item.episodes if not e.symlinked and e.file and e.folder]
            elif isinstance(existing_item, (Movie, Episode)):
                proposed_submissions = [existing_item]
            items_to_submit = []
            for sub_item in proposed_submissions:
                if Symlinker.should_submit(sub_item):
                    items_to_submit.append(sub_item)
                else:
                    logger.debug(f"{sub_item.log_string} not submitted to Symlinker because it is not eligible")

        elif existing_item.state == States.Symlinked:
            next_service = Updater
            items_to_submit = [existing_item]

        elif existing_item.state == States.Completed:
            return no_further_processing

    return existing_item, next_service, items_to_submit