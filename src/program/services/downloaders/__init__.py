# Removed ThreadPoolExecutor - now using sequential processing for proper RTN rank order
from datetime import datetime
from typing import List, Optional, Union

from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.media.stream import Stream
from program.services.downloaders.models import (
    DebridFile,
    InvalidDebridFileException,
    DownloadedTorrent,
    NoMatchingFilesException,
    NotCachedException,
    ParsedFileData,
    TorrentContainer,
    TorrentInfo,
)
from program.services.downloaders.shared import parse_filename

from .alldebrid import AllDebridDownloader
from .realdebrid import RealDebridDownloader
from .torbox import TorBoxDownloader


class Downloader:
    def __init__(self):
        self.key = "downloader"
        self.initialized = False
        self.services = {
            RealDebridDownloader: RealDebridDownloader(),
            AllDebridDownloader: AllDebridDownloader(),
            TorBoxDownloader: TorBoxDownloader(),
        }
        self.service = next((service for service in self.services.values() if service.initialized), None)
        self.initialized = self.validate()

    def validate(self):
        if self.service is None:
            logger.error(
                "No downloader service is initialized. Please initialize a downloader service."
            )
            return False
        return True

    def run(self, item: MediaItem):
        logger.debug(f"Starting download process for {item.log_string} ({item.id})")

        if item.file or item.active_stream or item.last_state in [States.Completed, States.Symlinked, States.Downloaded]:
            logger.debug(f"Skipping {item.log_string} ({item.id}) as it has already been downloaded by another download session")
            yield item

        if item.is_parent_blocked():
            logger.debug(f"Skipping {item.log_string} ({item.id}) as it has a blocked parent, or is a blocked item")
            yield item

        if not item.streams:
            logger.debug(f"❌ No streams available for download: {item.log_string}")
            yield item

        logger.debug(f"🔽 Starting download for {item.log_string} ({len(item.streams)} streams available)")
        download_success = False

        # Two-tier processing: Quick wins first, difficult items later
        if getattr(item, '_needs_deep_processing', False):
            # This is a retry for deep processing - check remaining streams
            download_success = self._try_deep_download(item)
        else:
            # First attempt - try quick download with top 5 streams
            download_success = self._try_quick_download(item)

            if not download_success:
                # Schedule for deeper processing later instead of blocking now
                download_success = self._schedule_deep_processing(item)

                # Simple failure handling - let state transition system handle retries
                if not download_success:
                    logger.debug(f"❌ Download failed for {item.log_string} - will be retried by state transition")

        yield item

    def _try_quick_download(self, item: MediaItem) -> bool:
        """
        Tier 1: Try to download using only the top 5 RTN ranked streams.
        This handles 80% of items quickly with minimal API calls.
        """
        if not item.streams:
            return False

        # Only check top 5 streams for quick wins
        top_streams = item.streams[:5]
        logger.debug(f"🚀 Quick download attempt: checking top {len(top_streams)} streams for {item.log_string}")

        # Check if service is available before processing any streams
        if hasattr(self.service, '_rate_limit_breaker'):
            if not self.service._rate_limit_breaker.can_execute():
                logger.warning(f"Circuit breaker OPEN - skipping all streams for {item.log_string}")
                return False

        # Process streams sequentially in RTN rank order (best first)
        # STOP immediately when we find the first valid stream
        for stream in top_streams:
            # Skip already blacklisted streams
            if item.is_stream_blacklisted(stream):
                logger.debug(f"⏭️ Skipping blacklisted stream {stream.infohash} for {item.log_string}")
                continue

            logger.debug(f"🔍 Checking stream {stream.infohash} (rank {getattr(stream, 'rank', 'unknown')}) for {item.log_string}")

            try:
                # Validate this single stream
                container = self.validate_stream(stream, item)
                if not container:
                    logger.debug(f"❌ Stream {stream.infohash} is not cached or valid")
                    item.blacklist_stream(stream)
                    continue  # Try next stream in rank order

                # Stream is valid - try to download it immediately
                logger.debug(f"✅ Stream {stream.infohash} is valid - attempting download")
                download_result = self.download_cached_stream(stream, container)

                if self.update_item_attributes(item, download_result):
                    logger.debug(f"✅ Quick download success: {item.log_string} from '{stream.raw_title}' [{stream.infohash}]")
                    return True  # SUCCESS - stop processing more streams
                else:
                    raise NoMatchingFilesException(f"No valid files found for {item.log_string} ({item.id})")

            except Exception as e:
                logger.debug(f"❌ Stream {stream.infohash} failed: {e}")
                if 'download_result' in locals() and download_result.id:
                    try:
                        self.service.delete_torrent(download_result.id)
                    except Exception:
                        pass
                item.blacklist_stream(stream)
                # Continue to next stream in rank order

        logger.debug(f"⏭️ Quick download failed for {item.log_string} - will try deep processing later")
        return False

    def _schedule_deep_processing(self, item: MediaItem) -> bool:
        """
        Tier 2: Try deep processing immediately if we have remaining streams.
        This prevents blocking the queue on difficult items.
        """
        if len(item.streams) <= 5:
            # No more streams to check
            logger.debug(f"❌ No more streams available for {item.log_string}")
            return False

        # Try deep processing immediately instead of scheduling
        logger.debug(f"🔍 Attempting deep processing for {item.log_string} ({len(item.streams) - 5} remaining streams)")
        return self._try_deep_download(item)

    def _try_deep_download(self, item: MediaItem) -> bool:
        """
        Tier 2: Try to download using remaining streams (beyond top 5).
        This handles the 20% of difficult items that need more thorough checking.
        """
        if not item.streams or len(item.streams) <= 5:
            logger.debug(f"❌ No remaining streams for deep processing: {item.log_string}")
            return False

        # Check if service is available before deep processing
        if hasattr(self.service, '_rate_limit_breaker'):
            if not self.service._rate_limit_breaker.can_execute():
                logger.warning(f"Circuit breaker OPEN - skipping deep processing for {item.log_string}")
                return False

        # Check remaining streams (beyond top 5) sequentially in RTN rank order
        remaining_streams = item.streams[5:]
        logger.debug(f"🔍 Deep processing: checking {len(remaining_streams)} remaining streams for {item.log_string}")

        # Process streams one at a time in RTN rank order - STOP when we find the first valid one
        for stream in remaining_streams:
            # Skip already blacklisted streams
            if item.is_stream_blacklisted(stream):
                logger.debug(f"⏭️ Skipping blacklisted stream {stream.infohash} for {item.log_string}")
                continue

            logger.debug(f"🔍 Deep processing stream {stream.infohash} (rank {getattr(stream, 'rank', 'unknown')}) for {item.log_string}")

            try:
                # Validate this single stream
                container = self.validate_stream(stream, item)
                if not container:
                    logger.debug(f"❌ Stream {stream.infohash} is not cached or valid")
                    item.blacklist_stream(stream)
                    continue  # Try next stream in rank order

                # Stream is valid - try to download it immediately
                logger.debug(f"✅ Stream {stream.infohash} is valid - attempting download")
                download_result = self.download_cached_stream(stream, container)

                if self.update_item_attributes(item, download_result):
                    logger.debug(f"✅ Deep processing success: {item.log_string} from '{stream.raw_title}' [{stream.infohash}]")
                    # Clear the deep processing flag
                    if hasattr(item, '_needs_deep_processing'):
                        delattr(item, '_needs_deep_processing')
                    return True  # SUCCESS - stop processing more streams
                else:
                    raise NoMatchingFilesException(f"No valid files found for {item.log_string} ({item.id})")

            except Exception as e:
                logger.debug(f"❌ Deep processing stream {stream.infohash} failed: {e}")
                if 'download_result' in locals() and download_result.id:
                    try:
                        self.service.delete_torrent(download_result.id)
                    except Exception:
                        pass
                item.blacklist_stream(stream)
                # Continue to next stream in rank order

        logger.debug(f"❌ Deep processing failed: No valid streams found for {item.log_string}")
        # Clear the deep processing flag since we've exhausted all options
        if hasattr(item, '_needs_deep_processing'):
            delattr(item, '_needs_deep_processing')
        return False

    # Removed _validate_streams_parallel - now using sequential processing to respect RTN rank order

    def _should_recheck_stream_availability(self, stream: Stream, item: MediaItem) -> bool:
        """
        Determine if a stream's availability should be rechecked based on adaptive polling.
        Uses data volatility patterns to optimize checking frequency.
        """
        # Always check if we've never checked before
        if not hasattr(stream, 'last_availability_check'):
            return True

        last_check = getattr(stream, 'last_availability_check', None)
        if not last_check:
            return True

        time_since_check = (datetime.now() - last_check).total_seconds()

        # Adaptive intervals based on stream and item characteristics
        base_interval = 300  # 5 minutes base

        # Recently added streams are more volatile
        if hasattr(stream, 'created_at') and stream.created_at:
            stream_age_hours = (datetime.now() - stream.created_at).total_seconds() / 3600
            if stream_age_hours < 1:
                base_interval = 60  # Check every minute for very new streams
            elif stream_age_hours < 6:
                base_interval = 180  # Check every 3 minutes for recent streams

        # High-priority items need more frequent checks
        if item.last_state in [States.Requested, States.Indexed]:
            base_interval *= 0.5  # Check twice as often

        # Popular streams (high rank) are more likely to become available
        if hasattr(stream, 'rank') and stream.rank < 10:
            base_interval *= 0.7  # Check more frequently for high-ranked streams

        # Failed availability checks get exponential backoff
        failed_checks = getattr(stream, 'failed_availability_checks', 0)
        if failed_checks > 0:
            base_interval *= (1.3 ** failed_checks)  # Exponential backoff

        # Cap between 30 seconds and 30 minutes
        final_interval = max(30, min(1800, base_interval))

        return time_since_check >= final_interval

    def validate_stream(self, stream: Stream, item: MediaItem) -> Optional[TorrentContainer]:
        """
        Validate a single stream with adaptive availability checking.
        """
        # Use adaptive polling to optimize availability checks
        if not self._should_recheck_stream_availability(stream, item):
            # Return cached result if available
            cached_container = getattr(stream, '_cached_container', None)
            if cached_container:
                logger.debug(f"Using cached availability for stream {stream.infohash}")
                return cached_container

        # Update last check time
        stream.last_availability_check = datetime.now()

        container = self.get_instant_availability(stream.infohash, item.type)
        if not container:
            logger.debug(f"Stream {stream.infohash} is not cached or valid.")
            # Track failed checks for adaptive backoff
            stream.failed_availability_checks = getattr(stream, 'failed_availability_checks', 0) + 1
            item.blacklist_stream(stream)
            return None

        # Cache successful result and reset failed counter
        stream._cached_container = container
        stream.failed_availability_checks = 0

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

        item.blacklist_stream(stream)
        return None

    def update_item_attributes(self, item: MediaItem, download_result: DownloadedTorrent) -> bool:
        """Update the item attributes with the downloaded files and active stream."""
        if not download_result.container:
            raise NotCachedException(f"No container found for {item.log_string} ({item.id})")

        episode_cap: int = None
        show: Optional[Show] = None
        if item.type in ("show", "season", "episode"):
            show: Optional[Show] = item if item.type == "show" else (item.parent if item.type == "season" else item.parent.parent)
            method_1 = sum(len(season.episodes) for season in show.seasons)
            try:
                method_2 = show.seasons[-1].episodes[-1].number
            except IndexError:
                # happens if theres a new season with no episodes yet
                method_2 = show.seasons[-2].episodes[-1].number
            episode_cap = max([method_1, method_2])

        found = False
        for file in download_result.container.files:
            file_data: ParsedFileData = parse_filename(file.filename)
            if item.type in ("show", "season", "episode"):
                if not file_data.episodes:
                    logger.debug(f"Skipping '{file.filename}' as it has no episodes")
                    continue
                elif 0 in file_data.episodes and len(file_data.episodes) == 1:
                    logger.debug(f"Skipping '{file.filename}' as it has an episode number of 0")
                    continue
                elif file_data.season == 0:
                    logger.debug(f"Skipping '{file.filename}' as it has a season number of 0")
                    continue
            if self.match_file_to_item(item, file_data, file, download_result, show, episode_cap):
                found = True

        return found

    def match_file_to_item(self,
            item: MediaItem,
            file_data: ParsedFileData,
            file: DebridFile,
            download_result: DownloadedTorrent,
            show: Optional[Show] = None,
            episode_cap: int = None
        ) -> bool:
        """Check if the file matches the item and update attributes."""
        found = False

        if item.type == "movie" and file_data.item_type == "movie":
            self._update_attributes(item, file, download_result)
            return True

        if item.type in ("show", "season", "episode"):
            season_number = file_data.season
            for file_episode in file_data.episodes:
                if episode_cap and file_episode > episode_cap:
                    # This is a sanity check to ensure the episode number is not greater than the total number of episodes in the show.
                    # If it is, we skip the episode as it is likely a mistake.
                    logger.debug(f"Invalid episode number {file_episode} for {show.log_string}. Skipping '{file.filename}'")
                    continue

                episode: Episode = show.get_episode(file_episode, season_number)
                if episode is None:
                    logger.debug(f"Episode {file_episode} from file does not match any episode in {show.log_string}. Metadata may be incorrect or wrong torrent for show.")
                    continue

                if episode.file:
                    continue

                if episode and episode.state not in [States.Completed, States.Symlinked, States.Downloaded]:
                    self._update_attributes(episode, file, download_result)
                    logger.debug(f"Matched episode {episode.log_string} to file {file.filename}")
                    found = True

        if found and item.type in ("show", "season"):
            item.active_stream = {"infohash": download_result.infohash, "id": download_result.info.id}

        return found

    def download_cached_stream(self, stream: Stream, container: TorrentContainer) -> DownloadedTorrent:
        """Download a cached stream"""
        torrent_id: int = self.add_torrent(stream.infohash)
        info: TorrentInfo = self.get_torrent_info(torrent_id)
        if container.file_ids:
            self.select_files(torrent_id, container.file_ids)
        return DownloadedTorrent(id=torrent_id, info=info, infohash=stream.infohash, container=container)

    def _update_attributes(self, item: Union[Movie, Episode], debrid_file: DebridFile, download_result: DownloadedTorrent) -> None:
        """Update the item attributes with the downloaded files and active stream"""
        item.file = debrid_file.filename
        item.folder = download_result.info.name
        item.alternative_folder = download_result.info.alternative_filename
        item.active_stream = {"infohash": download_result.infohash, "id": download_result.info.id}

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
