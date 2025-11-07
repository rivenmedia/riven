from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from loguru import logger
from RTN import ParsedData
from sqlalchemy import select

from program.db.db import db
from program.media.item import Episode, MediaItem, Movie, Show
from program.media.media_entry import MediaEntry
from program.media.state import States
from program.media.stream import Stream, StreamPendingRecord
from program.services.downloaders.models import (
    DebridFile,
    DownloadedTorrent,
    InvalidDebridFileException,
    NoMatchingFilesException,
    NotCachedException,
    TorrentContainer,
    TorrentInfo,
)
from program.services.downloaders.shared import _sort_streams_by_quality, parse_filename
from program.settings.manager import settings_manager
from program.utils.request import CircuitBreakerOpen

from .alldebrid import AllDebridDownloader
from .debridlink import DebridLinkDownloader
from .realdebrid import RealDebridDownloader

SERVICE_COOLDOWN_MIN_SECONDS = 30
SERVICE_COOLDOWN_MAX_SECONDS = 5 * 60
MAX_RESCHEDULE_SECONDS = 10 * 60


class Downloader:
    def __init__(self):
        self.key = "downloader"
        self.initialized = False
        self.services = {
            RealDebridDownloader: RealDebridDownloader(),
            DebridLinkDownloader: DebridLinkDownloader(),
            AllDebridDownloader: AllDebridDownloader(),
        }
        # Get all initialized services instead of just the first one
        self.initialized_services = [
            service for service in self.services.values() if service.initialized
        ]
        # Keep backward compatibility - primary service is the first initialized one
        self.service = (
            self.initialized_services[0] if self.initialized_services else None
        )
        self.initialized = self.validate()
        # Track circuit breaker retry attempts per item
        self._circuit_breaker_retries = {}
        # Track per-service cooldowns when circuit breaker is open
        self._service_cooldowns = {}  # {service.key: datetime}
        self._service_cooldown_backoff = defaultdict(
            lambda: SERVICE_COOLDOWN_MIN_SECONDS
        )
        # Track gate state to prevent spam logging
        self._gate_closed = False
        self._gate_closed_log_time = None

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

    def has_available_service(self) -> bool:
        """
        Check if any configured downloader service is currently available (not in cooldown).
        Does NOT perform health checks - those should be done separately when needed.
        """
        now = datetime.now()
        for service in self.initialized_services:
            # Check if service is still in cooldown
            if (
                service.key not in self._service_cooldowns
                or self._service_cooldowns[service.key] <= now
            ):
                return True
        return False

    def check_service_health(self) -> bool:
        """
        Perform a health check on available services (lightweight connectivity check without full validation).
        If any service fails the health check, reapply cooldown.
        This should be called sparingly and only when needed during circuit breaker recovery.
        """
        now = datetime.now()
        for service in self.initialized_services:
            # Check if service is still in cooldown
            if (
                service.key in self._service_cooldowns
                and self._service_cooldowns[service.key] > now
            ):
                continue

            # Try a lightweight responsiveness check (no premium logging, just connectivity)
            try:
                if service.is_responsive():
                    logger.debug(
                        f"Service {service.key} health check passed - service is responsive"
                    )
                    return True
                else:
                    # Service not responsive, reapply cooldown
                    cooldown_seconds = self._service_cooldown_backoff[service.key]
                    self._service_cooldowns[service.key] = now + timedelta(
                        seconds=cooldown_seconds
                    )
                    self._service_cooldown_backoff[service.key] = min(
                        cooldown_seconds * 2, SERVICE_COOLDOWN_MAX_SECONDS
                    )
                    logger.warning(
                        f"Service {service.key} health check failed (returned False), reapplying {cooldown_seconds}s cooldown"
                    )
                    continue
            except CircuitBreakerOpen:
                # Circuit breaker tripped during health check
                cooldown_seconds = self._service_cooldown_backoff[service.key]
                self._service_cooldowns[service.key] = now + timedelta(
                    seconds=cooldown_seconds
                )
                self._service_cooldown_backoff[service.key] = min(
                    cooldown_seconds * 2, SERVICE_COOLDOWN_MAX_SECONDS
                )
                logger.warning(
                    f"Service {service.key} circuit breaker opened during health check, reapplying {cooldown_seconds}s cooldown"
                )
                continue
            except Exception as e:
                # Health check threw exception, reapply cooldown
                cooldown_seconds = self._service_cooldown_backoff[service.key]
                self._service_cooldowns[service.key] = now + timedelta(
                    seconds=cooldown_seconds
                )
                self._service_cooldown_backoff[service.key] = min(
                    cooldown_seconds * 2, SERVICE_COOLDOWN_MAX_SECONDS
                )
                logger.warning(
                    f"Service {service.key} health check failed with exception: {e}, reapplying {cooldown_seconds}s cooldown"
                )
                continue

        return False

    def run(self, item: MediaItem):
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
            latest_allowed = datetime.now() + timedelta(seconds=MAX_RESCHEDULE_SECONDS)
            next_attempt = min(next_attempt, latest_allowed)
            wait_seconds = (next_attempt - datetime.now()).total_seconds()

            # Only log once per gate closure to avoid spam
            if not self._gate_closed:
                self._gate_closed = True
                self._gate_closed_log_time = now
                logger.warning(
                    f"Circuit breaker open: All downloader services in cooldown, rescheduling and waiting for gate to close for {wait_seconds:.0f}s"
                )

            yield (item, next_attempt)
            return

        # Gate is now open, reset the closed flag AND reset backoff counters on successful processing
        if self._gate_closed:
            self._gate_closed = False
            self._gate_closed_log_time = None
            # Only reset backoff counters when gate successfully opens, not on every call
            for service_key in self._service_cooldown_backoff:
                self._service_cooldown_backoff[service_key] = (
                    SERVICE_COOLDOWN_MIN_SECONDS
                )
            logger.info("Downloader services recovered, backoff reset to minimum")

        pending_candidates: list[tuple[int, Stream, str]] = []
        stream_rank: dict[Stream, int] = {}

        # Cache to store { (infohash, service.key): (service_instance, service_torrent_id) }
        torrent_id_cache = {}

        try:
            download_success = False
            # Sort streams by resolution and rank (highest first), with anime dub prioritization
            sorted_streams = _sort_streams_by_quality(item.streams, item)
            stream_rank = {stream: idx for idx, stream in enumerate(sorted_streams)}

            # Track if we hit circuit breaker on any service
            hit_circuit_breaker = False
            tried_streams = 0

            for stream in sorted_streams:
                # Try each available service for this stream before blacklisting
                stream_failed_on_all_services = True
                stream_hit_circuit_breaker = False

                for service in available_services:
                    if (
                        service.key in self._service_cooldowns
                        and self._service_cooldowns[service.key] > datetime.now()
                    ):
                        continue
                    logger.debug(
                        f"Trying stream {stream.infohash} on {service.key} for {item.log_string}"
                    )

                    try:
                        # Validate stream on this specific service
                        container = service.get_instant_availability(
                            stream.infohash, item.type
                        )

                        # Store the ID in the cache IMMEDIATELY
                        if container and container.torrent_id:
                            torrent_id_cache[(stream.infohash, service.key)] = (
                                service,
                                container.torrent_id,
                            )

                        # Now, validate the container
                        if not self.validate_stream_container(container, item):
                            logger.debug(
                                f"Stream {stream.infohash} not available on {service.key}"
                            )
                            continue

                        pending_count = len(getattr(container, "pending_files", []))
                        ready_count = len(getattr(container, "ready_files", []))
                        requires_full_pack = item.type in ("show", "season")

                        # Check if this stream has been pending for too long (likely a bad torrent)
                        # Query for existing pending record REGARDLESS of current pending_count
                        # (it may have gone ready temporarily then pending again)
                        now_time = datetime.now()
                        session = db.Session()
                        try:
                            stmt = select(StreamPendingRecord).where(
                                (StreamPendingRecord.media_item_id == item.id)
                                & (
                                    StreamPendingRecord.stream_infohash
                                    == stream.infohash
                                )
                            )
                            pending_record = session.execute(stmt).scalar_one_or_none()

                            if pending_count:
                                # Files are currently pending
                                if not pending_record:
                                    # First time seeing this stream in pending state, create record
                                    pending_record = StreamPendingRecord(
                                        media_item_id=item.id,
                                        stream_infohash=stream.infohash,
                                        pending_since=now_time,
                                    )
                                    session.add(pending_record)
                                    session.commit()

                            # Check timeout regardless of whether files are currently pending
                            if pending_record:
                                time_pending = (
                                    now_time - pending_record.pending_since
                                ).total_seconds()
                                pending_timeout = (
                                    settings_manager.settings.downloaders.pending_timeout_seconds
                                )

                                if time_pending > pending_timeout:
                                    logger.warning(
                                        f"Stream {stream.infohash} has been pending for {time_pending/3600:.1f}h for {item.log_string}; likely a bad torrent, blacklisting"
                                    )

                                    if container and container.torrent_id:
                                        try:
                                            service.delete_torrent(container.torrent_id)
                                            logger.debug(
                                                f"Deleted dead torrent {container.torrent_id} from {service.key}"
                                            )
                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to delete dead torrent {container.torrent_id} from {service.key}: {e}"
                                            )

                                    item.blacklist_stream(stream)
                                    # Delete the pending record
                                    session.delete(pending_record)
                                    session.commit()
                                    stream_failed_on_all_services = True
                                    break
                                elif not pending_count:
                                    # Files are no longer pending, but record exists - delete it
                                    session.delete(pending_record)
                                    session.commit()
                        finally:
                            session.close()

                        if pending_count and (requires_full_pack or ready_count == 0):
                            logger.info(
                                f"Stream {stream.infohash} cached on {service.key} but {pending_count} file(s) are still preparing; will retry later"
                            )
                            pending_candidates.append(
                                (pending_count, stream, service.key)
                            )
                            stream_failed_on_all_services = False
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
                            # Clean up pending record for this stream
                            session = db.Session()
                            try:
                                stmt = select(StreamPendingRecord).where(
                                    (StreamPendingRecord.media_item_id == item.id)
                                    & (
                                        StreamPendingRecord.stream_infohash
                                        == stream.infohash
                                    )
                                )
                                pending_record = session.execute(
                                    stmt
                                ).scalar_one_or_none()
                                if pending_record:
                                    session.delete(pending_record)
                                    session.commit()
                            finally:
                                session.close()
                            download_success = True
                            stream_failed_on_all_services = False
                            self._service_cooldown_backoff[service.key] = SERVICE_COOLDOWN_MIN_SECONDS
                            self._service_cooldowns.pop(service.key, None)
                            break
                        else:
                            raise NoMatchingFilesException(
                                f"No valid files found for {item.log_string} ({item.id})"
                            )

                    except CircuitBreakerOpen:
                        # Seed/extend per-service backoff safely
                        cooldown_seconds = self._service_cooldown_backoff.setdefault(
                            service.key, SERVICE_COOLDOWN_MIN_SECONDS
                        )
                        self._service_cooldowns[service.key] = datetime.now() + timedelta(seconds=cooldown_seconds)
                        self._service_cooldown_backoff[service.key] = min(
                            cooldown_seconds * 2, SERVICE_COOLDOWN_MAX_SECONDS
                        )

                        logger.warning(
                            f"Circuit breaker OPEN for {service.key}, backing off {cooldown_seconds}s before retry"
                        )

                        stream_hit_circuit_breaker = True
                        hit_circuit_breaker = True

                        # With a single initialized service, do not mark this stream as failed this tick;
                        # we'll reschedule after the loop using the min cooldown.
                        if len(self.initialized_services) == 1:
                            stream_failed_on_all_services = False

                        continue  # try next service for the same stream

                    except Exception as e:
                        logger.debug(
                            f"Stream {stream.infohash} failed on {service.key}: {e}"
                        )
                        if "download_result" in locals() and download_result.id:
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

                # If we didn’t succeed on any service but at least one service hit a circuit breaker,
                # reschedule the item for the earliest cooldown expiry instead of blacklisting.
                if not download_success and stream_hit_circuit_breaker:
                    if self._service_cooldowns:
                        next_attempt = min(self._service_cooldowns.values())
                    else:
                        # Fallback in case cooldowns were cleared; avoid tight spin
                        next_attempt = datetime.now() + timedelta(seconds=SERVICE_COOLDOWN_MIN_SECONDS)
                    # Cap the reschedule horizon
                    latest_allowed = datetime.now() + timedelta(seconds=MAX_RESCHEDULE_SECONDS)
                    next_attempt = min(next_attempt, latest_allowed)

                    logger.info(
                        f"Rescheduling {item.log_string} due to circuit breaker(s); "
                        f"next attempt at {next_attempt.strftime('%m/%d/%y %H:%M:%S')}"
                    )
                    yield (item, next_attempt)
                    return

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
                        # Clean up pending record when stream is blacklisted
                        session = db.Session()
                        try:
                            stmt = select(StreamPendingRecord).where(
                                (StreamPendingRecord.media_item_id == item.id)
                                & (
                                    StreamPendingRecord.stream_infohash
                                    == stream.infohash
                                )
                            )
                            pending_record = session.execute(stmt).scalar_one_or_none()
                            if pending_record:
                                session.delete(pending_record)
                                session.commit()
                        finally:
                            session.close()
                        item.blacklist_stream(stream)

                tried_streams += 1
                if tried_streams >= 3:
                    yield item

        except Exception as e:
            logger.error(
                f"Unexpected error in downloader for {item.log_string} ({item.id}): {e}"
            )

        if not download_success and pending_candidates:
            # Use the candidate with the fewest pending files and highest ranked stream
            pending_candidates.sort(key=lambda c: (c[0], stream_rank.get(c[1], 0)))
            best_pending, best_stream, service_key = pending_candidates[0]
            retry_delay = min(180, max(30, best_pending * 15))
            next_attempt = datetime.now() + timedelta(seconds=retry_delay)
            latest_allowed = datetime.now() + timedelta(seconds=MAX_RESCHEDULE_SECONDS)
            next_attempt = min(next_attempt, latest_allowed)
            logger.info(
                f"Deferring {item.log_string}: best cached stream {best_stream.infohash} on {service_key} still preparing {best_pending} file(s); rescheduling for {next_attempt.strftime('%m/%d/%y %H:%M:%S')}"
            )
            yield (item, next_attempt)
            return

        if not download_success:
            # Check if we hit circuit breaker in single-provider mode
            if hit_circuit_breaker and len(self.initialized_services) == 1:
                # Reschedule for after cooldown instead of failing
                next_attempt = min(self._service_cooldowns.values())
                latest_allowed = datetime.now() + timedelta(
                    seconds=MAX_RESCHEDULE_SECONDS
                )
                next_attempt = min(next_attempt, latest_allowed)
                logger.warning(
                    f"Single provider hit circuit breaker for {item.log_string} ({item.id}), rescheduling for {next_attempt.strftime('%m/%d/%y %H:%M:%S')}"
                )
                yield (item, next_attempt)
                return
            else:
                logger.debug(
                    f"Failed to download any streams for {item.log_string} ({item.id})"
                )
        else:
            # Clear retry count and service cooldowns on successful download
            self._circuit_breaker_retries.pop(item.id, None)
            self._service_cooldowns.clear()
            self._service_cooldown_backoff.clear()

        yield item

    def validate_stream(
        self, stream: Stream, item: MediaItem
    ) -> Optional[TorrentContainer]:
        """
        Validate a single stream by ensuring its files match the item's requirements.
        Uses the primary service for backward compatibility.
        """
        return self.validate_stream_on_service(stream, item, self.service)

    def validate_stream_on_service(
        self, stream: Stream, item: MediaItem, service
    ) -> Optional[TorrentContainer]:
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
            # Keep readiness metadata aligned with the filtered file list
            if hasattr(container, "ready_files"):
                container.ready_files = [
                    file.filename
                    for file in valid_files
                    if file.download_url and file.filename
                ]
            if hasattr(container, "pending_files"):
                container.pending_files = [
                    file.filename
                    for file in valid_files
                    if not file.download_url and file.filename
                ]
            return container

        return None

    def validate_stream_container(
        self, container: Optional[TorrentContainer], item: MediaItem
    ) -> bool:
        """
        Validates a container by ensuring its files match the item's requirements.
        This is the validation logic extracted from validate_stream_on_service.
        """
        if not container:
            return False

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
                logger.debug(f"{container.infohash}: {e}")
                continue

        if valid_files:
            container.files = valid_files
            # Keep readiness metadata aligned with the filtered file list
            if hasattr(container, "ready_files"):
                container.ready_files = [
                    file.filename
                    for file in valid_files
                    if file.download_url and file.filename
                ]
            if hasattr(container, "pending_files"):
                container.pending_files = [
                    file.filename
                    for file in valid_files
                    if not file.download_url and file.filename
                ]
            return True

        # No valid files found
        return False

    def update_item_attributes(
        self, item: MediaItem, download_result: DownloadedTorrent, service=None
    ) -> bool:
        """Update the item attributes with the downloaded files and active stream."""
        if service is None:
            service = self.service

        try:
            if not download_result.container:
                raise NotCachedException(
                    f"No container found for {item.log_string} ({item.id})"
                )

            episode_cap: int = None
            show: Optional[Show] = None
            if item.type in ("show", "season", "episode"):
                show = (
                    item
                    if item.type == "show"
                    else (item.parent if item.type == "season" else item.parent.parent)
                )
                try:
                    method_1 = sum(len(season.episodes) for season in show.seasons)
                    try:
                        method_2 = show.seasons[-1].episodes[-1].number
                    except IndexError:
                        # happens if theres a new season with no episodes yet
                        method_2 = show.seasons[-2].episodes[-1].number
                    episode_cap = max([method_1, method_2])
                except Exception:
                    pass
            found = False
            files = list(download_result.container.files or [])
            # Track episodes we've already processed to avoid duplicates
            processed_episode_ids: set[str] = set()

            for file in files:
                try:
                    file_data: ParsedData = parse_filename(file.filename)
                except Exception:
                    continue

                if item.type in ("show", "season", "episode"):
                    if (
                        not file_data.episodes
                        or 0 in file_data.episodes
                        and len(file_data.episodes) == 1
                        or file_data.seasons
                        and file_data.seasons[0] == 0
                    ):
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
        show: Optional[Show] = None,
        episode_cap: int = None,
        processed_episode_ids: Optional[set[str]] = None,
        service=None,
    ) -> bool:
        """
        Determine whether a parsed file corresponds to the given media item (movie, show, season, or episode) and update the item's attributes when matches are found.

        Checks movie matches for movie items and episode-level matches for shows/seasons/episodes. For each matched episode or movie file, calls _update_attributes to attach filesystem metadata and marks the item.active_stream when appropriate.

        Parameters:
            item (MediaItem): The target media item to match against.
            file_data (ParsedData): Parsed metadata from RTN (item type, season, episode list, etc.).
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

        logger.debug(
            f"match_file_to_item: item={item.id} type={item.type} file='{file.filename}'"
        )
        found = False

        if item.type == "movie" and file_data.type == "movie":
            logger.debug("match_file_to_item: movie match -> updating attributes")
            self._update_attributes(item, file, download_result, service, file_data)
            return True

        if item.type in ("show", "season", "episode"):
            season_number = file_data.seasons[0] if file_data.seasons else None
            for file_episode in file_data.episodes:
                if episode_cap and file_episode > episode_cap:
                    logger.debug(
                        f"Invalid episode number {file_episode} for {getattr(show, 'log_string', 'show?')}. Skipping '{file.filename}'"
                    )
                    continue

                episode: Episode = show.get_absolute_episode(
                    file_episode, season_number
                )
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

        if found and item.type in ("show", "season"):
            item.active_stream = {
                "infohash": download_result.infohash,
                "id": download_result.info.id,
            }

        return found

    def download_cached_stream(
        self, stream: Stream, container: TorrentContainer
    ) -> DownloadedTorrent:
        """Download a cached stream using the primary service"""
        return self.download_cached_stream_on_service(stream, container, self.service)

    def download_cached_stream_on_service(
        self, stream: Stream, container: TorrentContainer, service
    ) -> DownloadedTorrent:
        """
        Prepare and return a DownloadedTorrent for a stream using the given service.

        Uses values already present on `container` when available (e.g., `torrent_id`, `torrent_info`); otherwise adds the torrent and/or fetches its info from the service.

        Returns:
            DownloadedTorrent: An object containing the torrent id, torrent info, the stream's infohash, and the (possibly updated) container.
        """
        # Check if we already have a torrent_id from validation (Real-Debrid optimization)
        if container.torrent_id:
            torrent_id = container.torrent_id
            logger.debug(
                f"Reusing torrent_id {torrent_id} from validation for {stream.infohash}"
            )

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
            id=torrent_id, info=info, infohash=stream.infohash, container=container
        )

    def _update_attributes(
        self,
        item: Union[Movie, Episode],
        debrid_file: DebridFile,
        download_result: DownloadedTorrent,
        service=None,
        file_data: ParsedData = None,
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
            # Pass parsed_data to avoid re-parsing the filename later
            entry = MediaEntry.create_virtual_entry(
                original_filename=debrid_file.filename,
                download_url=debrid_file.download_url,
                provider=service.key,
                provider_download_id=str(download_result.info.id),
                file_size=debrid_file.filesize or 0,
                parsed_data=file_data.model_dump() if file_data else None,
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
        self, infohash: str, item_type: str
    ) -> List[TorrentContainer]:
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

    def get_user_info(self, service) -> Dict:
        """Get user information"""
        return service.get_user_info()
