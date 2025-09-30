from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from loguru import logger
from sqlalchemy.orm import object_session

from program.media.item import Episode, MediaItem, Movie, Show
from program.media.state import States
from program.media.stream import Stream
from program.media.filesystem_entry import FilesystemEntry
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
from program.services.downloaders.shared import _sort_streams_by_quality, parse_filename
from program.utils.request import CircuitBreakerOpen

from .realdebrid import RealDebridDownloader
from .torbox import TorBoxDownloader


class Downloader:
    def __init__(self):
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
        if not self.initialized_services:
            logger.error(
                "No downloader service is initialized. Please initialize a downloader service."
            )
            return False
        logger.info(f"Initialized {len(self.initialized_services)} downloader service(s): {', '.join(s.key for s in self.initialized_services)}")
        return True


    def run(self, item: MediaItem):
        logger.debug(f"Starting download process for {item.log_string} ({item.id})")

        # Check if all services are in cooldown due to circuit breaker
        now = datetime.now()
        available_services = [
            service for service in self.initialized_services
            if service.key not in self._service_cooldowns or self._service_cooldowns[service.key] <= now
        ]

        if not available_services:
            # All services are in cooldown, reschedule for the earliest available time
            next_attempt = min(self._service_cooldowns.values())
            logger.warning(f"All downloader services in cooldown for {item.log_string} ({item.id}), rescheduling for {next_attempt.strftime('%m/%d/%y %H:%M:%S')}")
            yield (item, next_attempt)
            return

        try:
            download_success = False
            # Sort streams by resolution and rank (highest first) using simple, fast sorting
            sorted_streams = _sort_streams_by_quality(item.streams)

            for stream in sorted_streams:
                # Try each available service for this stream before blacklisting
                stream_failed_on_all_services = True

                for service in available_services:
                    logger.debug(f"Trying stream {stream.infohash} on {service.key} for {item.log_string}")

                    try:
                        # Validate stream on this specific service
                        container: Optional[TorrentContainer] = self.validate_stream_on_service(stream, item, service)
                        if not container:
                            logger.debug(f"Stream {stream.infohash} not available on {service.key}")
                            continue

                        # Try to download using this service
                        download_result = self.download_cached_stream_on_service(stream, container, service)
                        if self.update_item_attributes(item, download_result, service):
                            logger.log("DEBRID", f"Downloaded {item.log_string} from '{stream.raw_title}' [{stream.infohash}] using {service.key}")
                            download_success = True
                            stream_failed_on_all_services = False
                            break
                        else:
                            raise NoMatchingFilesException(f"No valid files found for {item.log_string} ({item.id})")

                    except CircuitBreakerOpen as e:
                        # This specific service hit circuit breaker, set cooldown and try next service
                        cooldown_duration = timedelta(minutes=1)
                        self._service_cooldowns[service.key] = datetime.now() + cooldown_duration
                        logger.warning(f"Circuit breaker OPEN for {service.key}, trying next service for stream {stream.infohash}")
                        continue

                    except Exception as e:
                        logger.debug(f"Stream {stream.infohash} failed on {service.key}: {e}")
                        if "download_result" in locals() and download_result.id:
                            try:
                                service.delete_torrent(download_result.id)
                                logger.debug(f"Deleted failed torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}.")
                            except Exception as del_e:
                                logger.debug(f"Failed to delete torrent {stream.infohash} for {item.log_string} ({item.id}) on {service.key}: {del_e}")
                        continue

                # If stream succeeded on any service, we're done
                if download_success:
                    break

                # Only blacklist if stream failed on ALL available services
                if stream_failed_on_all_services:
                    logger.debug(f"Stream {stream.infohash} failed on all {len(available_services)} available service(s), blacklisting")
                    item.blacklist_stream(stream)

        except Exception as e:
            logger.error(f"Unexpected error in downloader for {item.log_string} ({item.id}): {e}")

        if not download_success:
            logger.debug(f"Failed to download any streams for {item.log_string} ({item.id})")
        else:
            # Clear retry count and service cooldowns on successful download
            self._circuit_breaker_retries.pop(item.id, None)
            self._service_cooldowns.clear()

        yield item

    def validate_stream(self, stream: Stream, item: MediaItem) -> Optional[TorrentContainer]:
        """
        Validate a single stream by ensuring its files match the item's requirements.
        Uses the primary service for backward compatibility.
        """
        return self.validate_stream_on_service(stream, item, self.service)

    def validate_stream_on_service(self, stream: Stream, item: MediaItem, service) -> Optional[TorrentContainer]:
        """
        Validate a single stream on a specific service by ensuring its files match the item's requirements.
        """
        container = service.get_instant_availability(stream.infohash, item.type)
        if not container:
            logger.debug(f"Stream {stream.infohash} is not cached or valid on {service.key}.")
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
        """Check if the file matches the item and update attributes."""
        if service is None:
            service = self.service

        logger.debug(f"match_file_to_item: item={item.id} type={item.type} file='{file.filename}'")
        found = False

        if item.type == "movie" and file_data.item_type == "movie":
            logger.debug("match_file_to_item: movie match -> updating attributes")
            self._update_attributes(item, file, download_result, service)
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
                    self._update_attributes(episode, file, download_result, service)
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
        """Download a cached stream using a specific service"""
        torrent_id: int = service.add_torrent(stream.infohash)
        if service.key == "torbox":
            for file in container.files:
                file.download_url = service.get_download_url(torrent_id, file.file_id)
        info: TorrentInfo = service.get_torrent_info(torrent_id)
        if container.file_ids:
            service.select_files(torrent_id, container.file_ids)
        return DownloadedTorrent(id=torrent_id, info=info, infohash=stream.infohash, container=container)

    def _update_attributes(self, item: Union[Movie, Episode], debrid_file: DebridFile, download_result: DownloadedTorrent, service=None) -> None:
        """Update the item attributes"""
        if service is None:
            service = self.service

        item.active_stream = {"infohash": download_result.infohash, "id": download_result.info.id}

        # Create FilesystemEntry for virtual file if download URL is available
        if debrid_file.download_url:
            session = object_session(item)
            path = f"/__incoming__/{item.id}/{debrid_file.filename}"
            filesystem_entry = session.query(FilesystemEntry).filter_by(path=path).first()
            if not filesystem_entry:
                filesystem_entry = FilesystemEntry.create_virtual_entry(
                    path=path,
                    download_url=debrid_file.download_url,
                    provider=service.key,
                    provider_download_id=str(download_result.info.id),
                    file_size=debrid_file.filesize or 0,
                    original_filename=debrid_file.filename,
                    original_folder=download_result.info.alternative_filename or download_result.info.name
                )
                session.add(filesystem_entry)
                session.flush()  # Ensure filesystem_entry.id is populated

            # Link via relationship so in-memory state is updated immediately
            item.filesystem_entry = filesystem_entry
            item.active_stream = {"infohash": download_result.infohash, "id": download_result.info.id}
            session.flush()

    def get_instant_availability(self, infohash: str, item_type: str) -> List[TorrentContainer]:
        """Check if the torrent is cached"""
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
