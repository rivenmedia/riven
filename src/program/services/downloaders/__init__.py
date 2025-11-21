from datetime import datetime, timedelta
from typing import Literal
from loguru import logger
from RTN import ParsedData

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.media.stream import Stream
from program.media.media_entry import MediaEntry
from program.media.models import MediaMetadata
from program.services.downloaders.models import (
    DebridFile,
    DownloadedTorrent,
    InvalidDebridFileException,
    NoMatchingFilesException,
    NotCachedException,
    TorrentContainer,
    TorrentInfo,
    UserInfo,
)
from program.services.downloaders.shared import (
    DownloaderBase,
    sort_streams_by_quality,
    parse_filename,
)
from program.utils.request import CircuitBreakerOpen
from program.core.runner import MediaItemGenerator, Runner, RunnerResult

from .realdebrid import RealDebridDownloader
from .debridlink import DebridLinkDownloader
from .alldebrid import AllDebridDownloader


class Downloader(Runner[None, DownloaderBase]):
    def __init__(self):
        self.initialized = False
        self.services = [
            RealDebridDownloader(),
            DebridLinkDownloader(),
            AllDebridDownloader(),
        ]

        # Get all initialized services instead of just the first one
        self.initialized_services = [
            service for service in self.services if service.initialized
        ]

        # Keep backward compatibility - primary service is the first initialized one
        self.service = (
            self.initialized_services[0] if self.initialized_services else None
        )

        self.initialized = self.validate()

        # Track per-service cooldowns when circuit breaker is open
        self._service_cooldowns: dict[str, datetime] = {}

    def validate(self):
        if not self.initialized_services:
            logger.error(
                "No downloader service is initialized. Please initialize a downloader service."
            )
            return False
        logger.info(
            f"Initialized {len(self.initialized_services)} downloader service(s): {', '.join(s.key for s in self.initialized_services)}"
        )
        return True

    def run(self, item: MediaItem) -> MediaItemGenerator:
        logger.debug(f"Starting download process for {item.log_string} ({item.id})")

        # Check if all services are in cooldown due to circuit breaker
        now = datetime.now()

        available_services = [
            service
            for service in self.initialized_services
            if service.key not in self._service_cooldowns
            or self._service_cooldowns[service.key] <= now
        ]

        if not available_services:
            # All services are in cooldown, reschedule for the earliest available time
            next_attempt = min(self._service_cooldowns.values())

            logger.warning(
                f"All downloader services in cooldown for {item.log_string} ({item.id}), rescheduling for {next_attempt.strftime('%m/%d/%y %H:%M:%S')}"
            )

            yield RunnerResult(media_items=[item], run_at=next_attempt)
            return

        download_success = False

        # Track if we hit circuit breaker on any service
        hit_circuit_breaker = False

        try:
            # Sort streams by resolution and rank (highest first) using simple, fast sorting
            sorted_streams = sort_streams_by_quality(item.streams)

            tried_streams = 0

            for stream in sorted_streams:
                # Try each available service for this stream before blacklisting
                stream_failed_on_all_services = True
                stream_hit_circuit_breaker = False

                for service in available_services:
                    logger.debug(
                        f"Trying stream {stream.infohash} on {service.key} for {item.log_string}"
                    )

                    download_result: DownloadedTorrent | None = None

                    try:
                        # Validate stream on this specific service
                        container = self.validate_stream_on_service(
                            stream,
                            item,
                            service,
                        )

                        if not container:
                            logger.debug(
                                f"Stream {stream.infohash} not available on {service.key}"
                            )
                            continue

                        # Try to download using this service
                        download_result = self.download_cached_stream_on_service(
                            stream, container, service
                        )

                        if self.update_item_attributes(item, download_result, service):
                            logger.log(
                                "DEBRID",
                                f"Downloaded {item.log_string} from '{stream.raw_title}' [{stream.infohash}] using {service.key}",
                            )

                            download_success = True
                            stream_failed_on_all_services = False

                            break
                        else:
                            raise NoMatchingFilesException(
                                f"No valid files found for {item.log_string} ({item.id})"
                            )
                    except CircuitBreakerOpen as e:
                        # This specific service hit circuit breaker, set cooldown and try next service
                        cooldown_duration = timedelta(minutes=1)
                        self._service_cooldowns[service.key] = (
                            datetime.now() + cooldown_duration
                        )
                        logger.warning(
                            f"Circuit breaker OPEN for {service.key}, trying next service for stream {stream.infohash}"
                        )
                        stream_hit_circuit_breaker = True
                        hit_circuit_breaker = True

                        # If this is the only initialized service, don't mark stream as failed
                        # We want to retry this stream after cooldown
                        if len(self.initialized_services) == 1:
                            stream_failed_on_all_services = False
                        continue

                    except Exception as e:
                        logger.debug(
                            f"Stream {stream.infohash} failed on {service.key}: {e}"
                        )

                        if download_result and download_result.id:
                            try:
                                service.delete_torrent(download_result.id)

                                logger.debug(
                                    f"Deleted failed torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}."
                                )
                            except Exception as del_e:
                                logger.debug(
                                    f"Failed to delete torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}: {del_e}"
                                )
                        continue

                # If stream succeeded on any service, we're done
                if download_success:
                    break

                # Only blacklist if stream genuinely failed on ALL available services
                # Don't blacklist if we hit circuit breaker in single-provider mode
                if stream_failed_on_all_services:
                    if (
                        stream_hit_circuit_breaker
                        and len(self.initialized_services) == 1
                    ):
                        logger.debug(
                            f"Stream {stream.infohash} hit circuit breaker on single provider, will retry after cooldown"
                        )
                    else:
                        logger.debug(
                            f"Stream {stream.infohash} failed on all {len(available_services)} available service(s), blacklisting"
                        )
                        item.blacklist_stream(stream)

                tried_streams += 1

                if tried_streams >= 3:
                    yield RunnerResult(media_items=[item])

        except Exception as e:
            logger.error(
                f"Unexpected error in downloader for {item.log_string} ({item.id}): {e}"
            )

        if not download_success:
            # Check if we hit circuit breaker in single-provider mode
            if hit_circuit_breaker and len(self.initialized_services) == 1:
                # Reschedule for after cooldown instead of failing
                next_attempt = min(self._service_cooldowns.values())

                logger.warning(
                    f"Single provider hit circuit breaker for {item.log_string} ({item.id}), rescheduling for {next_attempt.strftime('%m/%d/%y %H:%M:%S')}"
                )

                yield RunnerResult(media_items=[item], run_at=next_attempt)

                return
            else:
                logger.debug(
                    f"Failed to download any streams for {item.log_string} ({item.id})"
                )
        else:
            # Clear service cooldowns on successful download
            self._service_cooldowns.clear()

        yield RunnerResult(media_items=[item])

    def validate_stream(
        self,
        stream: Stream,
        item: MediaItem,
    ) -> TorrentContainer | None:
        """
        Validate a single stream by ensuring its files match the item's requirements.
        Uses the primary service for backward compatibility.
        """

        return self.validate_stream_on_service(stream, item, self.service)

    def validate_stream_on_service(
        self,
        stream: Stream,
        item: MediaItem,
        service: "DownloaderBase",
    ) -> TorrentContainer | None:
        """
        Validate a single stream on a specific service by ensuring its files match the item's requirements.
        """

        container = service.get_instant_availability(stream.infohash, item.type)

        if not container:
            logger.debug(
                f"Stream {stream.infohash} is not cached or valid on {service.key}."
            )
            return None

        valid_files = []

        for file in container.files or []:
            if isinstance(file, DebridFile):
                valid_files.append(file)
                continue

            try:
                debrid_file = DebridFile.create(
                    filename=file.filename,
                    filesize_bytes=file.filesize,
                    filetype=item.type,
                    file_id=file.file_id,
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

    def update_item_attributes(
        self,
        item: MediaItem,
        download_result: DownloadedTorrent,
        service: DownloaderBase | None = None,
    ) -> bool:
        """Update the item attributes with the downloaded files and active stream."""

        if service is None:
            service = self.service

        try:
            if not download_result.container:
                raise NotCachedException(
                    f"No container found for {item.log_string} ({item.id})"
                )

            episode_cap: int | None = None
            show: Show | None = None

            if isinstance(item, (Show, Season, Episode)):
                show = (
                    item
                    if isinstance(item, Show)
                    else (
                        item.parent if isinstance(item, Season) else item.parent.parent
                    )
                )

                try:
                    method_1 = sum(len(season.episodes) for season in show.seasons)

                    try:
                        method_2 = show.seasons[-1].episodes[-1].number
                    except IndexError:
                        # happens if there's a new season with no episodes yet
                        method_2 = show.seasons[-2].episodes[-1].number

                    episode_cap = max([method_1, method_2 or 0])
                except Exception as e:
                    pass

            found = False
            files = list(download_result.container.files or [])

            # Track episodes we've already processed to avoid duplicates
            processed_episode_ids: set[str] = set()

            for file in files:
                try:
                    assert file.filename

                    file_data: ParsedData = parse_filename(file.filename)
                except Exception as e:
                    continue

                if isinstance(item, (Show, Season, Episode)):
                    if not file_data.episodes:
                        continue
                    elif 0 in file_data.episodes and len(file_data.episodes) == 1:
                        continue
                    elif file_data.seasons and file_data.seasons[0] == 0:
                        continue

                if self.match_file_to_item(
                    item,
                    file_data,
                    file,
                    download_result,
                    show,
                    episode_cap,
                    processed_episode_ids,
                    service,
                ):
                    found = True

            return found
        except Exception as e:
            logger.debug(f"update_item_attributes: exception for item {item.id}: {e}")
            raise

    def match_file_to_item(
        self,
        item: MediaItem,
        file_data: ParsedData,
        file: DebridFile,
        download_result: DownloadedTorrent,
        show: Show | None = None,
        episode_cap: int | None = None,
        processed_episode_ids: set[str] | None = None,
        service: DownloaderBase | None = None,
    ) -> bool:
        """
        Determine whether a parsed file corresponds to the given media item (movie, show, season, or episode) and update the item's attributes when matches are found.

        Checks movie matches for movie items and episode-level matches for shows/seasons/episodes. For each matched episode or movie file, calls _update_attributes to attach filesystem metadata and marks the item.active_stream when appropriate.

        Parameters:
            item (MediaItem): The target media item to match against.
            file_data (ParsedData): Parsed metadata from RTN (item type, season, episode list, etc.).
            file (DebridFile): The debrid file candidate containing filename, download URL, and size.
            download_result (DownloadedTorrent): The download context containing infohash and torrent id.
            show (Show | None): The show object used to resolve absolute episode numbers when matching episodes.
            episode_cap (int, optional): Maximum episode number allowed for matching; episodes greater than this are skipped.
            processed_episode_ids (set[str] | None): Set of episode IDs already processed in this container to avoid duplicate updates.
            service (optional): Service instance used for attribute updates; defaults to the Downloader's primary service.

        Returns:
            bool: `true` if at least one file-to-item match was found and attributes were updated, `false` otherwise.
        """

        if service is None:
            service = self.service

        logger.debug(
            f"match_file_to_item: item={item.id} type={item.type} file='{file.filename}'"
        )

        found = False

        if isinstance(item, Movie) and file_data.type == "movie":
            logger.debug("match_file_to_item: movie match -> updating attributes")
            self._update_attributes(item, file, download_result, service, file_data)
            return True

        if isinstance(item, (Show, Season, Episode)):
            season_number = file_data.seasons[0] if file_data.seasons else None

            for file_episode in file_data.episodes:
                if episode_cap and file_episode > episode_cap:
                    logger.debug(
                        f"Invalid episode number {file_episode} for {getattr(show, 'log_string', 'show?')}. Skipping '{file.filename}'"
                    )
                    continue

                assert show

                episode = show.get_absolute_episode(file_episode, season_number)

                if episode is None:
                    logger.debug(
                        f"Episode {file_episode} from file does not match any episode in {getattr(show, 'log_string', 'show?')}"
                    )
                    continue

                if episode.filesystem_entry:
                    logger.debug(
                        f"Episode {episode.log_string} already has filesystem_entry; skipping"
                    )
                    continue

                if episode and episode.state not in [
                    States.Completed,
                    States.Symlinked,
                    States.Downloaded,
                ]:
                    # Skip if we've already processed this episode in this container
                    if (
                        processed_episode_ids is not None
                        and str(episode.id) in processed_episode_ids
                    ):
                        continue
                    logger.debug(
                        f"match_file_to_item: updating episode {episode.id} from file '{file.filename}'"
                    )
                    self._update_attributes(
                        episode, file, download_result, service, file_data
                    )
                    if processed_episode_ids is not None:
                        processed_episode_ids.add(str(episode.id))
                    logger.debug(
                        f"Matched episode {episode.log_string} to file {file.filename}"
                    )
                    found = True

        if found and isinstance(item, (Show, Season)):
            item.active_stream = Stream(
                torrent=download_result,
            )

        return found

    def download_cached_stream(
        self,
        stream: Stream,
        container: TorrentContainer,
    ) -> DownloadedTorrent:
        """Download a cached stream using the primary service"""

        assert self.service

        return self.download_cached_stream_on_service(stream, container, self.service)

    def download_cached_stream_on_service(
        self,
        stream: Stream,
        container: TorrentContainer,
        service: DownloaderBase,
    ) -> DownloadedTorrent:
        """
        Prepare and return a DownloadedTorrent for a stream using the given service.

        Uses values already present on `container` when available (e.g., `torrent_id`, `torrent_info`); otherwise adds the torrent and/or fetches its info from the service.

        Returns:
            DownloadedTorrent: An object containing the torrent id, torrent info, the stream's infohash, and the (possibly updated) container.
        """

        torrent_id = None

        # Check if we already have a torrent_id from validation (Real-Debrid optimization)
        if container.torrent_id:
            torrent_id = container.torrent_id

            logger.debug(
                f"Reusing torrent_id {torrent_id} from validation for {stream.infohash}"
            )

        assert torrent_id

        # Check if we already have torrent_info from validation (Real-Debrid optimization)
        if container.torrent_info:
            info = container.torrent_info
            logger.debug(f"Reusing cached torrent_info for {stream.infohash}")
        else:
            # Fallback: fetch info if not cached
            info: TorrentInfo = service.get_torrent_info(torrent_id)

        if container.file_ids:
            service.select_files(torrent_id, container.file_ids)

        return DownloadedTorrent(
            id=torrent_id,
            info=info,
            infohash=stream.infohash,
            container=container,
        )

    def _update_attributes(
        self,
        item: Movie | Episode,
        debrid_file: DebridFile,
        download_result: DownloadedTorrent,
        service: DownloaderBase | None = None,
        file_data: ParsedData | None = None,
    ) -> None:
        """
        Update the media item's active stream and filesystem entries using a debrid file from a completed download.

        Sets item.active_stream from the download_result and, if the debrid file exposes a download URL,
        creates a MediaEntry with the original filename, download URL, and provider information.
        Path generation is now handled by RivenVFS when the entry is registered.

        Parameters:
            item (Movie|Episode): The media item to update.
            debrid_file (DebridFile): Debrid file metadata (must include filename and optionally download_url and filesize).
            download_result (DownloadedTorrent): Result of the download containing id and infohash.
            service: Optional debrid service instance; defaults to the downloader's configured service.
            file_data (ParsedData, optional): Parsed filename metadata from RTN to cache in MediaEntry.
        """
        if service is None:
            service = self.service

        item.active_stream = {
            "infohash": download_result.infohash,
            "id": download_result.info.id,
        }

        # Create MediaEntry for virtual file if download URL is available
        if debrid_file.download_url:
            from program.services.library_profile_matcher import LibraryProfileMatcher

            # Match library profiles for this item
            matcher = LibraryProfileMatcher()
            library_profiles = matcher.get_matching_profiles(item)

            # Create MediaEntry with original_filename as source of truth
            # Path generation is now handled by RivenVFS during registration
            # Convert parsed file_data to MediaMetadata if available
            media_metadata = None

            if file_data:
                media_metadata = MediaMetadata.from_parsed_data(
                    parsed_data=file_data,
                    filename=debrid_file.filename,
                )

            assert debrid_file.filename
            assert service

            entry = MediaEntry.create_virtual_entry(
                original_filename=debrid_file.filename,
                download_url=debrid_file.download_url,
                provider=service.key,
                provider_download_id=str(download_result.info.id),
                file_size=debrid_file.filesize or 0,
                media_metadata=media_metadata,
            )

            # Populate library profiles
            entry.library_profiles = library_profiles

            # Clear existing entries and add the new one
            item.filesystem_entries.clear()
            item.filesystem_entries.append(entry)

            logger.debug(
                f"Created MediaEntry for {item.log_string} with original_filename={debrid_file.filename}"
            )
            if library_profiles:
                logger.debug(
                    f"Matched library profiles for {item.log_string}: {library_profiles}"
                )

    def get_instant_availability(
        self,
        infohash: str,
        item_type: Literal["movie", "show", "season", "episode"],
    ) -> TorrentContainer | None:
        """
        Retrieve cached availability information for a torrent identified by its infohash and item type.

        Queries the active downloader service for instant availability and returns any matching cached torrent containers.

        Returns:
            list[TorrentContainer]: A list of TorrentContainer objects representing available cached torrents; empty list if none are found.
        """

        assert self.service

        return self.service.get_instant_availability(infohash, item_type)

    def add_torrent(self, infohash: str) -> int | str:
        """Add a torrent by infohash"""

        assert self.service

        return self.service.add_torrent(infohash)

    def get_torrent_info(self, torrent_id: int | str) -> TorrentInfo | None:
        """Get information about a torrent"""

        assert self.service

        return self.service.get_torrent_info(torrent_id)

    def select_files(self, torrent_id: int | str, container: list[int]) -> None:
        """Select files from a torrent"""

        assert self.service

        self.service.select_files(torrent_id, container)

    def delete_torrent(self, torrent_id: int | str) -> None:
        """Delete a torrent"""

        assert self.service

        self.service.delete_torrent(torrent_id)

    def get_user_info(self, service: "DownloaderBase") -> UserInfo | None:
        """Get user information"""

        return service.get_user_info()
