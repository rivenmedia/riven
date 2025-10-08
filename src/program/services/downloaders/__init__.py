"""
Downloader service for Riven.

This module provides the main Downloader class that:
- Manages multiple debrid service providers (Real-Debrid, TorBox)
- Ranks and validates streams using RTN
- Downloads cached torrents from debrid services
- Updates MediaEntry objects with download results
- Handles pack downloads (season/show packs)
- Manages circuit breaker cooldowns for failed services
- Supports profile-specific downloads (4K, 1080p, etc.)

The Downloader processes MediaEntry objects (not MediaItem directly) to support
multiple scraping profiles per item.
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from loguru import logger
from RTN import RTN, sort_torrents

from program.media.item import Episode, MediaItem, Movie, Show
from program.media.state import States
from program.media.stream import Stream
from program.media.media_entry import MediaEntry
from program.services.downloaders.models import (
    DebridFile,
    DownloadedTorrent,
    InvalidDebridFileException,
    NoMatchingFilesException,
    NotCachedException,
    ParsedFileData,
    TorrentContainer,
    TorrentInfo,
)
from program.services.downloaders.shared import parse_filename
from program.utils.request import CircuitBreakerOpen
from program.settings.manager import settings_manager

from .realdebrid import RealDebridDownloader
from .torbox import TorBoxDownloader


class Downloader:
    """
    Main downloader service that manages debrid providers and downloads.

    Supports multiple debrid services with automatic fallback:
    - Real-Debrid
    - TorBox

    Key features:
    - Profile-aware downloads (processes MediaEntry objects)
    - Multi-provider fallback (tries all services before blacklisting)
    - Circuit breaker cooldowns (prevents hammering failed services)
    - Pack download support (season/show packs)
    - Stream ranking using RTN
    - MediaEntry-level stream blacklisting

    Attributes:
        key: Service identifier ("downloader").
        initialized: Whether at least one debrid service is initialized.
        services: Dict of all debrid service instances.
        initialized_services: List of successfully initialized services.
        service: Primary service (first initialized, for backward compatibility).
    """
    def __init__(self):
        """
        Initialize the Downloader service.

        Initializes all configured debrid services and sets up:
        - Service instances (Real-Debrid, TorBox)
        - Circuit breaker retry tracking
        - Per-service cooldowns
        """
        self.key = "downloader"
        self.initialized = False
        self.services = {
            RealDebridDownloader: RealDebridDownloader(),
            TorBoxDownloader: TorBoxDownloader(),
        }
        # Get all initialized services instead of just the first one
        self.initialized_services = [service for service in self.services.values() if service.initialized]
        # Keep backward compatibility - primary service is the first initialized one
        self.service = self.initialized_services[0] if self.initialized_services else None
        self.initialized = self.validate()
        # Track circuit breaker retry attempts per item
        self._circuit_breaker_retries = {}
        # Track per-service cooldowns when circuit breaker is open
        self._service_cooldowns = {}  # {service.key: datetime}

    def validate(self):
        """
        Validate that at least one debrid service is initialized.

        Returns:
            bool: True if at least one service is initialized, False otherwise.
        """
        if not self.initialized_services:
            logger.error(
                "No downloader service is initialized. Please initialize a downloader service."
            )
            return False
        logger.info(f"Initialized {len(self.initialized_services)} downloader service(s): {', '.join(s.key for s in self.initialized_services)}")
        return True


    def run(self, entry: MediaEntry):
        """
        Download media for a specific MediaEntry (profile-aware).

        The MediaEntry already knows:
        - Which profile it belongs to (entry.scraping_profile_name)
        - Which MediaItem it's for (entry.media_item)
        - Its current state (entry.state)

        This method:
        1. Ranks streams using the entry's profile ranking config
        2. Tries to download the best stream
        3. Updates the MediaEntry with download results
        4. Returns the entry object for state transition

        Note: Each MediaEntry is processed independently. Multiple profiles = multiple MediaEntries.
        """
        if not entry.media_item:
            logger.error(f"MediaEntry {entry.id} has no associated MediaItem")
            yield entry
            return

        item = entry.media_item
        profile_name = entry.scraping_profile_name

        logger.debug(f"Starting download for {item.log_string} [Profile: {profile_name}] (Entry ID: {entry.id})")

        # Check if all services are in cooldown due to circuit breaker
        now = datetime.now()
        available_services = [
            service for service in self.initialized_services
            if service.key not in self._service_cooldowns or self._service_cooldowns[service.key] <= now
        ]

        if not available_services:
            # All services are in cooldown, reschedule for the earliest available time
            next_attempt = min(self._service_cooldowns.values())
            logger.warning(f"All downloader services in cooldown for {entry.log_string}, rescheduling for {next_attempt.strftime('%m/%d/%y %H:%M:%S')}")
            yield (entry, next_attempt)
            return

        # Get the profile for this entry
        profile = next((p for p in settings_manager.settings.scraping_profiles if p.name == profile_name), None)
        if not profile:
            logger.error(f"Profile '{profile_name}' not found for {entry.log_string}")
            entry.failed = True
            yield entry
            return

        if not profile.enabled:
            logger.debug(f"Profile '{profile_name}' is disabled, skipping {entry.log_string}")
            yield entry
            return

        # Try to download for this entry
        try:
            success = self._download_for_entry(entry, item, profile, available_services)
            if success:
                # Clear retry count and service cooldowns on successful download
                self._circuit_breaker_retries.pop(entry.id, None)
                self._service_cooldowns.clear()
                logger.log("DEBRID", f"Successfully downloaded {entry.log_string}")
            else:
                logger.debug(f"Failed to download {entry.log_string}")
                # If download failed for an episode, consider re-scraping parent for more streams
                if item.type == "episode":
                    self._consider_parent_rescraping(item)
        except Exception as e:
            logger.error(f"Error downloading {entry.log_string}: {e}")
            entry.failed = True

        yield entry

    def _filter_blacklisted_streams(self, entry: MediaEntry, streams: List[Stream]) -> List[Stream]:
        """
        Filter out streams that have been blacklisted for this MediaEntry.

        Args:
            entry: The MediaEntry being processed
            streams: List of streams to filter

        Returns:
            List[Stream]: Streams that haven't been blacklisted for this entry
        """
        filtered_streams = [stream for stream in streams if not entry.is_stream_blacklisted(stream)]

        blacklisted_count = len(streams) - len(filtered_streams)
        if blacklisted_count > 0:
            logger.debug(f"Filtered out {blacklisted_count} blacklisted streams for {entry.log_string}")

        return filtered_streams

    def _get_streams_for_item(self, item: MediaItem) -> List[Stream]:
        """
        Get streams for an item, checking hierarchically for episodes.

        For episodes: checks Episode → Season → Show
        For other types: uses item.streams directly

        Returns:
            List[Stream]: Available streams for this item
        """
        # Check item's own streams first
        if item.streams:
            return item.streams

        # For episodes, check parent season and show
        if item.type == "episode":
            # Check season
            if item.parent and item.parent.streams:
                logger.debug(f"Using streams from season {item.parent.log_string} for episode {item.log_string}")
                return item.parent.streams

            # Check show
            if item.parent and item.parent.parent and item.parent.parent.streams:
                logger.debug(f"Using streams from show {item.parent.parent.log_string} for episode {item.log_string}")
                return item.parent.parent.streams

        return []

    def _consider_parent_rescraping(self, episode: MediaItem):
        """
        Consider re-scraping parent season/show when episode download fails.

        This handles the case where:
        1. Show gets scraped → episodes are enqueued
        2. Episodes fail to download (no suitable streams)
        3. Season/show might have more streams available if re-scraped

        Args:
            episode: The episode that failed to download
        """
        if episode.type != "episode":
            return

        from program.program import riven

        # Re-scrape the parent season or show to get more streams
        if episode.parent.parent.streams:
            logger.debug(f"Episode {episode.log_string} failed with show streams, re-scraping season")
            riven.em.add_item(episode.parent, service="Scraping")
            return
        elif episode.parent.streams:
            logger.debug(f"Episode {episode.log_string} failed with season streams, re-scraping episode")
            riven.em.add_item(episode, service="Scraping")
            return

    def _download_for_entry(self, entry: MediaEntry, item: MediaItem, profile, available_services: List) -> bool:
        """
        Download content for a specific MediaEntry.

        Updates the existing MediaEntry with download results.

        Returns:
            bool: True if download succeeded
        """
        logger.debug(f"Attempting download for {entry.log_string}")

        # Rank streams for this profile
        ranked_streams = self._rank_streams_for_entry(entry, item, profile)
        if not ranked_streams:
            logger.debug(f"No streams available for {entry.log_string}")
            entry.failed = True
            return False

        # Try to download using ranked streams
        success = self._try_download_streams(entry, item, ranked_streams, available_services)

        return success

    def _rank_streams_for_entry(self, entry: MediaEntry, item: MediaItem, profile) -> List[Stream]:
        """
        Rank item's streams using the entry's profile ranking configuration.
        Uses the same ranking approach as scrapers with sort_torrents.

        For episodes, checks hierarchically: Episode → Season → Show for streams.

        Returns:
            List[Stream]: Streams sorted by rank (best first)
        """
        # Get streams hierarchically for episodes
        streams = self._get_streams_for_item(item)
        if not streams:
            return []

        # Filter out streams that have already failed for this entry
        streams = self._filter_blacklisted_streams(entry, streams)
        if not streams:
            return []

        # Use RTN to rank streams with profile's ranking config (same as scrapers)
        # Get correct title for ranking
        correct_title = item.get_top_title()

        rtn = RTN(profile)

        # Convert streams back to Torrent objects for ranking
        torrents = set()
        for stream in streams:
            try:
                # Recreate Torrent object from Stream data
                torrent = rtn.rank(
                    raw_title=stream.raw_title,
                    infohash=stream.infohash,
                    correct_title=correct_title,
                    speed_mode=True,
                    remove_trash=True
                )
                torrents.add(torrent)
            except Exception as e:
                logger.debug(f"Failed to rank stream {stream.infohash}: {e}")
                continue

        if not torrents:
            return []

        # Use sort_torrents like scrapers do
        sorted_torrents = sort_torrents(torrents, bucket_limit=settings_manager.settings.scraping.bucket_limit)

        # Convert back to Stream objects in ranked order
        ranked_streams = []
        for torrent in sorted_torrents.values():
            # Find the corresponding Stream object
            stream = next((s for s in streams if s.infohash == torrent.infohash), None)
            if stream:
                ranked_streams.append(stream)

        logger.debug(f"Ranked {len(ranked_streams)} streams for {entry.log_string}")
        if ranked_streams:
            top_3 = ranked_streams[:3]
            logger.debug(f"Top 3 streams: {[f'{stream.raw_title}' for stream in top_3]}")

        return ranked_streams

    def _try_download_streams(self, entry: MediaEntry, item: MediaItem, ranked_streams: List[Stream], available_services: List) -> bool:
        """
        Try to download from ranked streams for a MediaEntry.

        Updates the MediaEntry with download results.

        Returns:
            bool: True if download succeeded
        """
        logger.debug(f"Attempting download for {entry.log_string} with {len(ranked_streams)} ranked streams")

        for stream in ranked_streams:
            # Try each available service for this stream before blacklisting
            stream_failed_on_all_services = True
            stream_hit_circuit_breaker = False

            for service in available_services:
                logger.debug(f"Trying stream {stream.infohash} on {service.key} for {entry.log_string}")

                try:
                    # Validate stream on this specific service
                    container: Optional[TorrentContainer] = self.validate_stream_on_service(stream, item, service)
                    if not container:
                        logger.debug(f"Stream {stream.infohash} not available on {service.key}")
                        continue

                    # Try to download using this service
                    download_result = self.download_cached_stream_on_service(stream, container, service)
                    if self._update_entry_with_download(entry, item, download_result, service, stream):
                        logger.log("DEBRID", f"Downloaded {entry.log_string} from '{stream.raw_title}' [{stream.infohash}] using {service.key}")
                        stream_failed_on_all_services = False
                        return True
                    else:
                        raise NoMatchingFilesException(f"No valid files found for {entry.log_string}")

                except CircuitBreakerOpen as e:
                    # This specific service hit circuit breaker, set cooldown and try next service
                    cooldown_duration = timedelta(minutes=1)
                    self._service_cooldowns[service.key] = datetime.now() + cooldown_duration
                    logger.warning(f"Circuit breaker OPEN for {service.key}, trying next service for stream {stream.infohash}")
                    stream_hit_circuit_breaker = True

                    # If this is the only initialized service, don't mark stream as failed
                    if len(self.initialized_services) == 1:
                        stream_failed_on_all_services = False
                    continue

                except Exception as e:
                    logger.debug(f"Stream {stream.infohash} failed on {service.key} for {entry.log_string}: {e}")
                    if "download_result" in locals() and download_result.id:
                        try:
                            service.delete_torrent(download_result.id)
                            logger.debug(f"Deleted failed torrent {stream.infohash} on {service.key}")
                        except Exception as del_e:
                            logger.debug(f"Failed to delete torrent {stream.infohash} on {service.key}: {del_e}")
                    continue

            # Handle stream failure - blacklist for this specific MediaEntry
            if stream_failed_on_all_services:
                if stream_hit_circuit_breaker and len(self.initialized_services) == 1:
                    logger.debug(f"Stream {stream.infohash} hit circuit breaker on single provider, will retry after cooldown")
                else:
                    logger.debug(f"Stream {stream.infohash} failed on all {len(available_services)} available service(s) for {entry.log_string}")
                    # Blacklist stream for this specific MediaEntry
                    entry.blacklist_stream(stream)
                    entry.failed = True

        return False

    def _update_entry_with_download(self, entry: MediaEntry, item: MediaItem, download_result: DownloadedTorrent, service, stream: Stream) -> bool:
        """
        Update MediaEntry objects with download results.

        For movies: Updates the entry with the movie file
        For episodes: Finds the matching episode file and updates the entry
        For packs (show/season): Updates ALL matching episode entries

        Returns:
            bool: True if at least one entry was successfully updated
        """
        from program.services.filesystem.path_utils import generate_target_path
        from program.settings.manager import settings_manager

        try:
            if not download_result.container:
                raise NotCachedException(f"No container found for {item.log_string}")

            files = list(download_result.container.files or [])
            logger.debug(f"Processing {len(files)} file(s) from torrent for {entry.log_string}")

            matched_entries = []  # Track all entries we update

            for file in files:
                try:
                    file_data: ParsedFileData = parse_filename(file.filename)
                except Exception as e:
                    logger.debug(f"Failed to parse filename '{file.filename}': {e}")
                    continue

                # For movies, update entry with the movie file
                if item.type == "movie" and file_data.item_type == "movie":
                    # Generate VFS path
                    vfs_path = generate_target_path(
                        item,
                        settings_manager.settings.filesystem,
                        original_filename=file.filename,
                        profile_name=entry.scraping_profile_name
                    )

                    # Update MediaEntry
                    entry.path = vfs_path
                    entry.download_url = file.download_url
                    entry.provider = service.key
                    entry.provider_download_id = str(download_result.id)
                    entry.file_size = file.filesize
                    entry.original_filename = file.filename
                    entry.active_stream = {"infohash": stream.infohash, "raw_title": stream.raw_title}
                    entry.failed = False

                    # Populate filename parsing fields from Stream's parsed_data (RTN data)
                    entry.parsed = stream.parsed_data

                    logger.debug(f"Updated MediaEntry for {item.log_string} at {vfs_path}")
                    matched_entries.append(entry)
                    # For movies, we're done after first match
                    break

                # For episodes, match the file to this specific episode
                if item.type == "episode":
                    if not file_data.episodes:
                        continue
                    elif 0 in file_data.episodes and len(file_data.episodes) == 1:
                        continue
                    elif file_data.season == 0:
                        continue

                    # Check if this file matches our episode
                    if item.number in file_data.episodes or (item.absolute_number and item.absolute_number in file_data.episodes):
                        # This file matches our episode
                        vfs_path = generate_target_path(
                            item,
                            settings_manager.settings.filesystem,
                            original_filename=file.filename,
                            profile_name=entry.scraping_profile_name
                        )

                        # Update MediaEntry
                        entry.path = vfs_path
                        entry.download_url = file.download_url
                        entry.provider = service.key
                        entry.provider_download_id = str(download_result.id)
                        entry.file_size = file.filesize
                        entry.original_filename = file.filename
                        entry.active_stream = {"infohash": stream.infohash, "raw_title": stream.raw_title}
                        entry.failed = False

                        # Populate filename parsing fields from Stream's parsed_data (RTN data)
                        entry.parsed = stream.parsed_data

                        logger.debug(f"Updated MediaEntry for {item.log_string} at {vfs_path}")
                        matched_entries.append(entry)
                        # For single episode, we're done
                        break

            # Check if this is a pack download (multiple files matched)
            # If so, we need to update OTHER episode entries that match files in the pack
            if len(files) > 1 and item.type == "episode":
                # This might be a season/show pack - check if other episodes can be matched
                matched_entries.extend(
                    self._update_pack_entries(entry, item, files, download_result, service, stream)
                )

            if matched_entries:
                logger.info(f"Updated {len(matched_entries)} MediaEntry object(s) from pack download")
                return True

            logger.warning(f"No matching file found for {entry.log_string} in {len(files)} file(s)")
            return False

        except Exception as e:
            logger.error(f"_update_entry_with_download: exception for {entry.log_string}: {e}")
            raise

    def _update_pack_entries(self, triggering_entry: MediaEntry, item: MediaItem, files: list, download_result: DownloadedTorrent, service, stream: Stream) -> list[MediaEntry]:
        """
        Update other MediaEntry objects when a pack (season/show) is downloaded.

        When an episode triggers a download and the torrent contains multiple episode files,
        we need to:
        1. Update the MediaEntry objects for those other episodes
        2. Remove their Downloader events from the queue
        3. Add FilesystemService events for them instead

        Args:
            triggering_entry: The MediaEntry that triggered this download
            item: The episode MediaItem that triggered the download
            files: List of files in the downloaded torrent
            download_result: The download result
            service: The debrid service used
            stream: The stream that was downloaded

        Returns:
            List of MediaEntry objects that were updated
        """
        from program.services.filesystem.path_utils import generate_target_path
        from program.settings.manager import settings_manager
        from program.db.db import db

        updated_entries = []

        # Get the parent (season or show) to find sibling episodes
        parent = item.parent  # Season
        if not parent:
            return updated_entries

        # Get all episodes in the same season
        sibling_episodes = list(parent.episodes) if hasattr(parent, 'episodes') else []
        if not sibling_episodes:
            return updated_entries

        logger.debug(f"Checking pack download: {len(files)} files, {len(sibling_episodes)} episodes in {parent.log_string}")

        # Match each file to episodes
        for file in files:
            try:
                file_data: ParsedFileData = parse_filename(file.filename)
            except Exception as e:
                logger.debug(f"Failed to parse filename '{file.filename}': {e}")
                continue

            if not file_data.episodes:
                continue

            # Find episodes that match this file
            for episode in sibling_episodes:
                # Skip the triggering episode (already updated)
                if episode.id == item.id:
                    continue

                # Check if this file matches this episode
                if episode.number not in file_data.episodes and (not episode.absolute_number or episode.absolute_number not in file_data.episodes):
                    continue

                # Find the MediaEntry for this episode with the same profile
                with db.Session() as session:
                    episode_entry = session.query(MediaEntry).filter(
                        MediaEntry.media_item_id == episode.id,
                        MediaEntry.scraping_profile_name == triggering_entry.scraping_profile_name
                    ).first()

                    if not episode_entry:
                        logger.debug(f"No MediaEntry found for {episode.log_string} with profile '{triggering_entry.scraping_profile_name}'")
                        continue

                    # Skip if already downloaded
                    if episode_entry.download_url:
                        logger.debug(f"MediaEntry for {episode.log_string} already has download_url, skipping")
                        continue

                    # Generate VFS path
                    vfs_path = generate_target_path(
                        episode,
                        settings_manager.settings.filesystem,
                        original_filename=file.filename,
                        profile_name=triggering_entry.scraping_profile_name
                    )

                    # Update the MediaEntry
                    episode_entry.path = vfs_path
                    episode_entry.download_url = file.download_url
                    episode_entry.provider = service.key
                    episode_entry.provider_download_id = str(download_result.id)
                    episode_entry.file_size = file.filesize
                    episode_entry.original_filename = file.filename
                    episode_entry.active_stream = {"infohash": stream.infohash, "raw_title": stream.raw_title}
                    episode_entry.failed = False

                    # Populate filename parsing fields from Stream's parsed_data (RTN data)
                    if hasattr(stream, 'parsed_data') and stream.parsed_data:
                        parsed = stream.parsed_data
                        episode_entry.filename_parsed_resolution = parsed.resolution
                        episode_entry.filename_parsed_quality = parsed.quality
                        episode_entry.filename_parsed_codec = parsed.codec
                        episode_entry.filename_parsed_hdr = parsed.hdr
                        episode_entry.filename_parsed_audio = parsed.audio

                    session.commit()
                    logger.info(f"Updated MediaEntry for {episode.log_string} from pack download")
                    updated_entries.append(episode_entry)

                    # Update the event queue: remove Downloader event, add FilesystemService event
                    self._update_entry_queue(episode_entry)

        if updated_entries:
            logger.info(f"Pack download: Updated {len(updated_entries)} additional MediaEntry objects")

        return updated_entries

    def _update_entry_queue(self, entry: MediaEntry):
        """
        Update the event queue for an entry that was downloaded as part of a pack.

        Removes any queued Downloader events and adds a FilesystemService event instead.

        Args:
            entry: The MediaEntry that was updated
        """
        from program.services.filesystem.filesystem_service import FilesystemService
        from program.types import Event
        from program.program import riven

        try:
            # Remove any queued Downloader events for this entry
            # This prevents the entry from trying to download again
            riven.em.cancel_job(entry.id, is_entry=True)
            logger.debug(f"Removed Downloader event for {entry.log_string} from queue")

            # Add FilesystemService event to register the file in VFS
            # The entry is now in Downloaded state, so it will go directly to FilesystemService
            riven.em.add_event(Event(FilesystemService, entry_id=entry.id))
            logger.debug(f"Added FilesystemService event for {entry.log_string} to queue")

        except Exception as e:
            logger.error(f"Failed to update event queue for {entry.log_string}: {e}")

    def validate_stream(self, stream: Stream, item: MediaItem) -> Optional[TorrentContainer]:
        """
        Validate a single stream by ensuring its files match the item's requirements.
        Uses the primary service for backward compatibility.
        """
        return self.validate_stream_on_service(stream, item, self.service)

    def validate_stream_on_service(self, stream: Stream, item: MediaItem, service) -> Optional[TorrentContainer]:
        """
        Validate a single stream on a specific service by ensuring its files match the item's requirements.

        For episodes, accepts show packs, season packs, and single episodes.
        """
        # For episodes, we need to accept show/season packs, so use "show" as the type
        # This allows the debrid service to return all files in the torrent
        lookup_type = "show" if item.type == "episode" else item.type

        container = service.get_instant_availability(stream.infohash, lookup_type)
        if not container:
            logger.debug(f"Stream {stream.infohash} is not cached or valid on {service.key}.")
            return None

        valid_files = []
        for file in container.files or []:
            if isinstance(file, DebridFile):
                valid_files.append(file)
                continue

            try:
                # For validation, use "episode" filetype for episodes to apply correct filesize constraints
                # This accepts show packs, season packs, and single episodes
                validation_type = "episode" if item.type == "episode" else item.type

                debrid_file = DebridFile.create(
                    filename=file.filename,
                    filesize_bytes=file.filesize,
                    filetype=validation_type,
                    file_id=file.file_id
                )

                if isinstance(debrid_file, DebridFile):
                    valid_files.append(debrid_file)
            except InvalidDebridFileException as e:
                logger.debug(f"{stream.infohash}: {e}")
                continue

        if valid_files:
            container.files = valid_files
            return container

        return None

    def _find_existing_entry_for_profile(self, item: MediaItem, profile) -> Optional['MediaEntry']:
        """
        DEPRECATED: Legacy helper for finding MediaEntry by profile.
        Kept for backward compatibility with update_entry_with_download().
        """
        from program.media.media_entry import MediaEntry

        for entry in item.filesystem_entries:
            if isinstance(entry, MediaEntry) and entry.scraping_profile_name == profile.name:
                return entry
        return None

    def update_entry_with_download(self, item: MediaItem, download_result: DownloadedTorrent, service, profile, stream: Stream) -> bool:
        """
        DEPRECATED: Legacy method for creating MediaEntry for downloaded files.

        This method is kept for backward compatibility but should not be used in new code.
        Use _update_entry_with_download() instead, which updates existing MediaEntries.

        For movies: Creates one MediaEntry for the movie file
        For episodes: May create multiple MediaEntry instances if torrent contains multiple episodes (show/season pack)

        Returns:
            bool: True if at least one MediaEntry was created
        """
        from program.media.media_entry import MediaEntry
        from program.services.filesystem.path_utils import generate_target_path
        from program.settings.manager import settings_manager

        try:
            if not download_result.container:
                raise NotCachedException(f"No container found for {item.log_string}")

            # Get show for episode matching
            episode_cap: int = None
            show: Optional[Show] = None
            if item.type == "episode":
                show = item.parent.parent  # Episode → Season → Show
                try:
                    method_1 = sum(len(season.episodes) for season in show.seasons)
                    try:
                        method_2 = show.seasons[-1].episodes[-1].number
                    except IndexError:
                        method_2 = show.seasons[-2].episodes[-1].number
                    episode_cap = max([method_1, method_2])
                except Exception:
                    pass

            found = False
            files = list(download_result.container.files or [])

            logger.debug(f"Processing {len(files)} file(s) from torrent for {item.log_string} (profile: '{profile.name}')")

            for file in files:
                try:
                    file_data: ParsedFileData = parse_filename(file.filename)
                except Exception as e:
                    logger.debug(f"Failed to parse filename '{file.filename}': {e}")
                    continue

                # For movies, create MediaEntry directly
                if item.type == "movie" and file_data.item_type == "movie":
                    # Check if entry already exists for this profile
                    existing_entry = self._find_existing_entry_for_profile(item, profile)
                    if existing_entry:
                        logger.debug(f"Movie {item.log_string} already has entry for profile '{profile.name}'; skipping")
                        found = True
                        continue

                    # Generate VFS path
                    vfs_path = generate_target_path(
                        item,
                        settings_manager.settings.filesystem,
                        original_filename=file.filename,
                        profile_name=profile.name
                    )

                    # Create MediaEntry
                    entry = MediaEntry.create_virtual_entry(
                        path=vfs_path,
                        download_url=file.download_url,
                        provider=service.key,
                        provider_download_id=str(download_result.id),
                        file_size=file.filesize,
                        original_filename=file.filename,
                        scraping_profile_name=profile.name
                    )
                    entry.active_stream = {"infohash": stream.infohash, "raw_title": stream.raw_title}

                    # Populate filename parsing fields from Stream's parsed_data (RTN data)
                    # This avoids re-parsing in post-processing
                    if hasattr(stream, 'parsed_data') and stream.parsed_data:
                        parsed = stream.parsed_data
                        entry.filename_parsed_resolution = parsed.resolution
                        entry.filename_parsed_quality = parsed.quality
                        entry.filename_parsed_codec = parsed.codec
                        entry.filename_parsed_hdr = parsed.hdr
                        entry.filename_parsed_audio = parsed.audio

                    item.filesystem_entries.append(entry)
                    found = True
                    logger.debug(f"Created MediaEntry for {item.log_string} at {vfs_path} for profile '{profile.name}'")
                    break

                # For episodes, match files to individual episodes
                if item.type == "episode":
                    if not file_data.episodes:
                        logger.debug(f"Skipping '{file.filename}': no episode numbers found")
                        continue
                    elif 0 in file_data.episodes and len(file_data.episodes) == 1:
                        logger.debug(f"Skipping '{file.filename}': episode 0 (special/extra)")
                        continue
                    elif file_data.season == 0:
                        logger.debug(f"Skipping '{file.filename}': season 0 (specials)")
                        continue

                    season_number = file_data.season
                    for file_episode in file_data.episodes:
                        if episode_cap and file_episode > episode_cap:
                            logger.debug(f"Invalid episode number {file_episode} for {show.log_string}. Skipping '{file.filename}'")
                            continue

                        episode: Episode = show.get_absolute_episode(file_episode, season_number)
                        if episode is None:
                            logger.debug(f"Episode {file_episode} from file does not match any episode in {show.log_string}")
                            continue

                        # Skip episodes that are already completed/downloaded/symlinked
                        from program.media.state import States
                        if episode.last_state in [States.Completed, States.Symlinked, States.Downloaded]:
                            logger.debug(f"Episode {episode.log_string} already in state {episode.last_state.value}; skipping")
                            continue

                        # Check if this episode already has an entry for this profile
                        existing_episode_entry = self._find_existing_entry_for_profile(episode, profile)
                        if existing_episode_entry:
                            from program.media.entry_state import EntryState
                            if existing_episode_entry.state in [EntryState.Downloaded, EntryState.Available, EntryState.Completed]:
                                logger.debug(f"Episode {episode.log_string} already has successful entry for profile '{profile.name}' (state: {existing_episode_entry.state.value}); skipping")
                                continue
                            else:
                                logger.debug(f"Episode {episode.log_string} has existing entry for profile '{profile.name}' in state {existing_episode_entry.state.value}; will retry")

                        # Generate VFS path for this episode
                        vfs_path = generate_target_path(
                            episode,
                            settings_manager.settings.filesystem,
                            original_filename=file.filename,
                            profile_name=profile.name
                        )

                        # Create MediaEntry for this episode
                        entry = MediaEntry.create_virtual_entry(
                            path=vfs_path,
                            download_url=file.download_url,
                            provider=service.key,
                            provider_download_id=str(download_result.id),
                            file_size=file.filesize,
                            original_filename=file.filename,
                            scraping_profile_name=profile.name
                        )
                        entry.active_stream = {"infohash": stream.infohash, "raw_title": stream.raw_title}

                        # Populate filename parsing fields from Stream's parsed_data (RTN data)
                        # This avoids re-parsing in post-processing
                        if hasattr(stream, 'parsed_data') and stream.parsed_data:
                            parsed = stream.parsed_data
                            entry.filename_parsed_resolution = parsed.resolution
                            entry.filename_parsed_quality = parsed.quality
                            entry.filename_parsed_codec = parsed.codec
                            entry.filename_parsed_hdr = parsed.hdr
                            entry.filename_parsed_audio = parsed.audio

                        episode.filesystem_entries.append(entry)
                        found = True
                        logger.debug(f"Created MediaEntry for {episode.log_string} at {vfs_path} for profile '{profile.name}'")

            if not found:
                logger.warning(f"No valid files matched for {item.log_string} (profile: '{profile.name}') from {len(files)} file(s) in torrent")
                if item.type == "episode":
                    logger.debug(f"Looking for episodes in {show.log_string}: {[f'{s.number}x{e.number}' for s in show.seasons for e in s.episodes]}")

            return found
        except Exception as e:
            logger.debug(f"update_entry_with_download: exception for item {item.id} profile '{profile.name}': {e}")
            raise

    def update_item_attributes(self, item: MediaItem, download_result: DownloadedTorrent, service=None) -> bool:
        """Update the item attributes with the downloaded files and active stream."""
        if service is None:
            service = self.service

        try:
            if not download_result.container:
                raise NotCachedException(f"No container found for {item.log_string} ({item.id})")

            episode_cap: int = None
            show: Optional[Show] = None
            if item.type in ("show", "season", "episode"):
                show = item if item.type == "show" else (item.parent if item.type == "season" else item.parent.parent)
                try:
                    method_1 = sum(len(season.episodes) for season in show.seasons)
                    try:
                        method_2 = show.seasons[-1].episodes[-1].number
                    except IndexError:
                        # happens if theres a new season with no episodes yet
                        method_2 = show.seasons[-2].episodes[-1].number
                    episode_cap = max([method_1, method_2])
                except Exception as e:
                    pass
            found = False
            files = list(download_result.container.files or [])
            # Track episodes we've already processed to avoid duplicates
            processed_episode_ids: set[str] = set()

            for file in files:
                try:
                    file_data: ParsedFileData = parse_filename(file.filename)
                except Exception as e:
                    continue

                if item.type in ("show", "season", "episode"):
                    if not file_data.episodes:
                        continue
                    elif 0 in file_data.episodes and len(file_data.episodes) == 1:
                        continue
                    elif file_data.season == 0:
                        continue

                if self.match_file_to_item(item, file_data, file, download_result, show, episode_cap, processed_episode_ids, service):
                    found = True

            return found
        except Exception as e:
            logger.debug(f"update_item_attributes: exception for item {item.id}: {e}")
            raise

    def match_file_to_item(self,
            item: MediaItem,
            file_data: ParsedFileData,
            file: DebridFile,
            download_result: DownloadedTorrent,
            show: Optional[Show] = None,
            episode_cap: int = None,
            processed_episode_ids: Optional[set[str]] = None,
            service = None
        ) -> bool:
        """
            Determine whether a parsed file corresponds to the given media item (movie, show, season, or episode) and update the item's attributes when matches are found.
            
            Checks movie matches for movie items and episode-level matches for shows/seasons/episodes. For each matched episode or movie file, calls _update_attributes to attach filesystem metadata and marks the item.active_stream when appropriate.
            
            Parameters:
                item (MediaItem): The target media item to match against.
                file_data (ParsedFileData): Parsed metadata from the filename (item type, season, episode list, etc.).
                file (DebridFile): The debrid file candidate containing filename, download URL, and size.
                download_result (DownloadedTorrent): The download context containing infohash and torrent id.
                show (Optional[Show]): The show object used to resolve absolute episode numbers when matching episodes.
                episode_cap (int, optional): Maximum episode number allowed for matching; episodes greater than this are skipped.
                processed_episode_ids (Optional[set[str]]): Set of episode IDs already processed in this container to avoid duplicate updates.
                service (optional): Service instance used for attribute updates; defaults to the Downloader's primary service.
            
            Returns:
                bool: `true` if at least one file-to-item match was found and attributes were updated, `false` otherwise.
            """
        if service is None:
            service = self.service

        logger.debug(f"match_file_to_item: item={item.id} type={item.type} file='{file.filename}'")
        found = False

        if item.type == "movie" and file_data.item_type == "movie":
            logger.debug("match_file_to_item: movie match -> updating attributes")
            self._update_attributes(item, file, download_result, service, file_data)

            return True

        if item.type in ("show", "season", "episode"):
            season_number = file_data.season
            for file_episode in file_data.episodes:
                if episode_cap and file_episode > episode_cap:
                    logger.debug(f"Invalid episode number {file_episode} for {getattr(show, 'log_string', 'show?')}. Skipping '{file.filename}'")
                    continue

                episode: Episode = show.get_absolute_episode(file_episode, season_number)
                if episode is None:
                    logger.debug(f"Episode {file_episode} from file does not match any episode in {getattr(show, 'log_string', 'show?')}")
                    continue

                if episode.filesystem_entry:
                    logger.debug(f"Episode {episode.log_string} already has filesystem_entry; skipping")
                    continue

                if episode and episode.state not in [States.Completed, States.Symlinked, States.Downloaded]:
                    # Skip if we've already processed this episode in this container
                    if processed_episode_ids is not None and str(episode.id) in processed_episode_ids:
                        continue
                    logger.debug(f"match_file_to_item: updating episode {episode.id} from file '{file.filename}'")
                    self._update_attributes(episode, file, download_result, service, file_data)
                    if processed_episode_ids is not None:
                        processed_episode_ids.add(str(episode.id))
                    logger.debug(f"Matched episode {episode.log_string} to file {file.filename}")

                    found = True

        if found and item.type in ("show", "season"):
            item.active_stream = {"infohash": download_result.infohash, "id": download_result.info.id}

        return found

    def download_cached_stream(self, stream: Stream, container: TorrentContainer) -> DownloadedTorrent:
        """Download a cached stream using the primary service"""
        return self.download_cached_stream_on_service(stream, container, self.service)

    def download_cached_stream_on_service(self, stream: Stream, container: TorrentContainer, service) -> DownloadedTorrent:
        """
        Prepare and return a DownloadedTorrent for a stream using the given service.
        
        Uses values already present on `container` when available (e.g., `torrent_id`, `torrent_info`); otherwise adds the torrent and/or fetches its info from the service. For services with key "torbox" it populates each container file's `download_url`. If `container.file_ids` is set the service will be asked to select those files.
        
        Returns:
            DownloadedTorrent: An object containing the torrent id, torrent info, the stream's infohash, and the (possibly updated) container.
        """
        # Check if we already have a torrent_id from validation (Real-Debrid optimization)
        if container.torrent_id:
            torrent_id = container.torrent_id
            logger.debug(f"Reusing torrent_id {torrent_id} from validation for {stream.infohash}")
        else:
            # Fallback: add torrent if not cached (e.g., TorBox or old flow)
            torrent_id: int = service.add_torrent(stream.infohash)

        if service.key == "torbox":
            for file in container.files:
                file.download_url = service.get_download_url(torrent_id, file.file_id)

        # Check if we already have torrent_info from validation (Real-Debrid optimization)
        if container.torrent_info:
            info = container.torrent_info
            logger.debug(f"Reusing cached torrent_info for {stream.infohash}")
        else:
            # Fallback: fetch info if not cached
            info: TorrentInfo = service.get_torrent_info(torrent_id)

        if container.file_ids:
            service.select_files(torrent_id, container.file_ids)

        return DownloadedTorrent(id=torrent_id, info=info, infohash=stream.infohash, container=container)

    def _update_attributes(self, item: Union[Movie, Episode], debrid_file: DebridFile, download_result: DownloadedTorrent, service=None, file_data: ParsedFileData = None) -> None:
        """
        Update the media item's active stream and filesystem entries using a debrid file from a completed download.
        
        Sets item.active_stream from the download_result and, if the debrid file exposes a download URL, computes a virtual filesystem path (using the item, current filesystem settings, original filename, and optional parsed file data), creates a virtual FilesystemEntry containing provider, provider download id, file size, and original filename, and replaces the item's filesystem_entries with that single entry.
        
        Parameters:
            item (Movie|Episode): The media item to update.
            debrid_file (DebridFile): Debrid file metadata (must include filename and optionally download_url and filesize).
            download_result (DownloadedTorrent): Result of the download containing id and infohash.
            service: Optional debrid service instance; defaults to the downloader's configured service.
            file_data (ParsedFileData, optional): Parsed filename metadata to influence path generation; may be omitted.
        """
        if service is None:
            service = self.service

        item.active_stream = {"infohash": download_result.infohash, "id": download_result.info.id}

        # Create FilesystemEntry for virtual file if download URL is available
        if debrid_file.download_url:
            from program.services.filesystem.path_utils import generate_target_path
            from program.settings.manager import settings_manager

            vfs_path = generate_target_path(
                item,
                settings_manager.settings.filesystem,
                original_filename=debrid_file.filename,
                file_data=file_data
            )

            entry = MediaEntry.create_virtual_entry(
                path=vfs_path,
                download_url=debrid_file.download_url,
                provider=service.key,
                provider_download_id=str(download_result.info.id),
                file_size=debrid_file.filesize or 0,
                original_filename=debrid_file.filename,
            )

            # Clear existing entries and add the new one
            item.filesystem_entries.clear()
            item.filesystem_entries.append(entry)

            logger.debug(f"Created FilesystemEntry for {item.log_string} at {vfs_path}")

    def get_instant_availability(self, infohash: str, item_type: str) -> List[TorrentContainer]:
        """
        Retrieve cached availability information for a torrent identified by its infohash and item type.
        
        Queries the active downloader service for instant availability and returns any matching cached torrent containers.
        
        Returns:
            List[TorrentContainer]: A list of TorrentContainer objects representing available cached torrents; empty list if none are found.
        """
        return self.service.get_instant_availability(infohash, item_type)

    def add_torrent(self, infohash: str) -> int:
        """Add a torrent by infohash"""
        return self.service.add_torrent(infohash)

    def get_torrent_info(self, torrent_id: int) -> TorrentInfo:
        """Get information about a torrent"""
        return self.service.get_torrent_info(torrent_id)

    def select_files(self, torrent_id: int, container: list[str]) -> None:
        """Select files from a torrent"""
        self.service.select_files(torrent_id, container)

    def delete_torrent(self, torrent_id: int) -> None:
        """Delete a torrent"""
        self.service.delete_torrent(torrent_id)

    def resolve_link(self, link: str) -> Optional[Dict]:
        """Resolve a link to a download URL"""
        return self.service.resolve_link(link)
    
    def get_user_info(self, service) -> Dict:
        """Get user information"""
        return service.get_user_info()
    
    
