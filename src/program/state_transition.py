"""
State transition logic for Riven.

This module handles state machine transitions for both MediaItem and MediaEntry objects:

MediaItem State Machine (profile-agnostic):
- Requested → IndexerService (fetch metadata)
- Indexed → Scraping (find streams)
- Scraped → EntryCreator (create MediaEntry objects per profile)
- Ongoing → Re-scrape incomplete children
- Completed/Failed/Paused → No further processing

MediaEntry State Machine (profile-specific):
- Pending → Downloader (download file)
- Downloading → Downloader (check status)
- Downloaded → FilesystemService (add to VFS)
- Available → Updater (notify media servers)
- Completed → PostProcessing (analyze, fetch subtitles)
- Failed → No further processing

Key architectural notes:
- Shows/Seasons only go through: Requested → Indexed → Scraped → Ongoing/Completed
- Movies/Episodes go through full download pipeline
- MediaEntries are profile-aware (one per scraping profile)
- State transitions route events through appropriate services
"""
from typing import TYPE_CHECKING, Optional

from loguru import logger

from program.media import States
from program.media.entry_state import EntryState
from program.services.downloaders import Downloader
from program.services.entry_creator import EntryCreator
from program.services.indexers import IndexerService
from program.services.post_processing import PostProcessing
from program.services.scrapers import Scraping
from program.services.updaters import Updater
from program.services.filesystem import FilesystemService
from program.types import ProcessedEvent, Service

if TYPE_CHECKING:
    from program.media import MediaItem
    from program.media.media_entry import MediaEntry


def process_event(emitted_by: Service, existing_item: Optional["MediaItem"] = None, content_item: Optional["MediaItem"] = None) -> ProcessedEvent:
    """
    Process an event and return the updated item, next service and items/entries to submit.

    State transitions:
    - Requested → IndexerService
    - Indexed → Scraping (hierarchical: Show → Seasons → Episodes)
    - Scraped → Create MediaEntries → Enqueue MediaEntries for Downloader (Movies/Episodes only)
    - Downloaded → FilesystemService (only Movies/Episodes)
    - Symlinked → Updater (only Movies/Episodes)
    - Completed → PostProcessing + notify

    Shows/Seasons only go through: Requested → Indexed → Scraped → Ongoing/Completed
    Only Movies/Episodes go through the download pipeline.

    Returns:
        ProcessedEvent: Tuple of (next_service, items_or_entries_to_submit)
        items_or_entries_to_submit can contain MediaItem or MediaEntry objects
    """
    next_service: Service = None
    no_further_processing: ProcessedEvent = (None, [])
    items_to_submit = []

    if existing_item and existing_item.last_state in [States.Paused, States.Failed]:
        # logger.debug(f"Skipping {existing_item.log_string}: Item is {existing_item.last_state.name}. Manual intervention required.")
        return no_further_processing

    if content_item or (existing_item is not None and existing_item.last_state == States.Requested):
        next_service = IndexerService
        log_string = None
        if existing_item:
            log_string = existing_item.log_string
        elif content_item:
            log_string = content_item.log_string
        logger.debug(f"Submitting {log_string} to IndexerService")
        return next_service, [content_item or existing_item]

    elif existing_item is not None and existing_item.last_state == States.Ongoing:
        # Ongoing shows/seasons: re-scrape for new episodes
        if existing_item.type == "show":
            incomplete_seasons = [s for s in existing_item.seasons if s.last_state not in [States.Completed, States.Unreleased]]
            for season in incomplete_seasons:
                _, sub_items = process_event(emitted_by, season, None)
                items_to_submit += sub_items
        elif existing_item.type == "season":
            incomplete_episodes = [e for e in existing_item.episodes if e.last_state != States.Completed]
            for episode in incomplete_episodes:
                _, sub_items = process_event(emitted_by, episode, None)
                items_to_submit += sub_items

    elif existing_item is not None and existing_item.last_state == States.Indexed:
        next_service = Scraping
        if emitted_by != Scraping and Scraping.should_submit(existing_item):
            items_to_submit = [existing_item]
        elif existing_item.type == "show":
            items_to_submit = [s for s in existing_item.seasons if s.last_state in [States.Indexed, States.Ongoing, States.Unknown] and Scraping.should_submit(s)]
        elif existing_item.type == "season":
            items_to_submit = [e for e in existing_item.episodes if e.last_state in [States.Indexed, States.Unknown] and Scraping.should_submit(e)]

    elif existing_item is not None and existing_item.last_state == States.Scraped:
        # Scraped → Submit to EntryCreator to create MediaEntries
        # EntryCreator will create MediaEntry objects and yield them
        # They'll be saved by run_thread_with_db_item and then enqueued for download
        next_service = EntryCreator
        items_to_submit = [existing_item]
        logger.debug(f"Submitting {existing_item.log_string} to EntryCreator")

    if items_to_submit:
        service_name = next_service.__name__ if next_service else "StateTransition"
        logger.debug(f"State transition complete: {len(items_to_submit)} items/entries queued for {service_name}")

    return next_service, items_to_submit


def process_entry_event(emitted_by: Service, existing_entry: Optional["MediaEntry"] = None, content_entry: Optional["MediaEntry"] = None) -> ProcessedEvent:
    """
    Process a MediaEntry event and return the next service and entries to submit.

    MediaEntry State Transitions:
    - Pending → Downloader (retry download if failed)
    - Downloading → Downloader (check download status)
    - Downloaded → FilesystemService (add to VFS)
    - Available → PostProcessing (analyze media, fetch subtitles)
    - Completed → No further processing
    - Failed → No further processing (manual intervention required)

    MediaEntries are profile-aware and represent a single downloaded version of a MediaItem.
    Unlike MediaItems which are profile-agnostic, MediaEntries track the download/processing
    lifecycle for a specific scraping profile.

    Args:
        emitted_by: The service that emitted this event
        existing_entry: Existing MediaEntry from database
        content_entry: New MediaEntry to be processed

    Returns:
        Tuple of (next_service, entries_to_submit)
    """
    next_service: Service = None
    no_further_processing: ProcessedEvent = (None, [])
    entries_to_submit = []

    # Get the entry to process
    entry = existing_entry or content_entry
    if not entry:
        logger.error("process_entry_event called with no entry")
        return no_further_processing

    # Get entry state
    entry_state = entry.state

    # Failed entries require manual intervention
    if entry.failed:
        logger.debug(f"Skipping {entry.log_string}: Entry is marked as failed. Manual intervention required.")
        return no_further_processing

    # State-based transitions
    if entry_state == EntryState.Pending:
        # Pending entries need to be downloaded
        # Note: Downloader will handle profile-aware stream selection
        next_service = Downloader
        entries_to_submit = [entry]
        logger.debug(f"Submitting {entry.log_string} to Downloader (Pending → Downloading)")

    elif entry_state == EntryState.Downloading:
        # Check download status - Downloader will update entry state
        next_service = Downloader
        entries_to_submit = [entry]
        logger.debug(f"Checking download status for {entry.log_string}")

    elif entry_state == EntryState.Downloaded:
        # Downloaded entries need to be added to VFS
        next_service = FilesystemService
        entries_to_submit = [entry]
        logger.debug(f"Submitting {entry.log_string} to FilesystemService (Downloaded → Available)")

    elif entry_state == EntryState.Available:
        # Available entries need to be checked for updates
        if emitted_by != Updater:
            next_service = Updater
            # Submit the entry itself for update checking
            entries_to_submit = [entry]
            logger.debug(f"Submitting {entry.log_string} to Updater (Available → Completed)")
        else:
            # Already checked for updates
            return no_further_processing

    elif entry_state == EntryState.Completed:
        if emitted_by != PostProcessing:
            next_service = PostProcessing
            entries_to_submit = [entry]
            logger.debug(f"Submitting {entry.log_string} to PostProcessing")
        else:
            return no_further_processing

    else:
        logger.warning(f"Unknown entry state {entry_state} for {entry.log_string}")
        return no_further_processing

    if entries_to_submit:
        service_name = next_service.__name__ if next_service else "StateTransition"
        logger.debug(f"Entry state transition complete: {len(entries_to_submit)} entries queued for {service_name}")

    return next_service, entries_to_submit
