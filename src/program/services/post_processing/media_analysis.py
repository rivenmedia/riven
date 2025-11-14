"""
Media Analysis Service for Riven.

Analyzes media files using ffprobe and RTN to extract:
- Video/audio codec information
- Embedded subtitle tracks
- Parsed metadata from filename (resolution, codec, audio, etc.)

This service runs once per item before subtitle fetching to populate
metadata that can be used for intelligent subtitle selection and
upgrade decisions.
"""

import traceback

from loguru import logger

from program.utils.ffprobe import parse_media_url
from program.media.models import MediaMetadata
from program.media.item import MediaItem
from program.media.media_entry import MediaEntry


class MediaAnalysisService:
    """Service for analyzing media files and extracting metadata."""

    def __init__(self):
        self.key = "media_analysis"
        self.initialized = True
        logger.info("Media Analysis service initialized")

    @property
    def enabled(self) -> bool:
        """Media analysis is always enabled as it's a core service."""
        return True

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        """
        Determine if media analysis should run for this item.

        Only runs once per item when:
        - Item has a filesystem entry
        - Entry hasn't been analyzed yet (no media_metadata with probed_at timestamp)
        - Item type is movie or episode

        Args:
            item: MediaItem to check

        Returns:
            True if analysis should run, False otherwise
        """
        if item.type not in ["movie", "episode"]:
            return False

        if not item.filesystem_entry:
            return False

        # Skip if already probed (check for probed_at timestamp in media_metadata)
        if item.filesystem_entry.media_metadata:
            metadata = item.filesystem_entry.media_metadata
            if metadata.get("probed_at"):
                return False

        return True

    def run(self, item: MediaItem) -> bool:
        """
        Analyze media file and store metadata.

        Performs:
        1. FFprobe analysis (video/audio codecs, embedded subtitles, actual resolution)
        2. Updates existing MediaMetadata (created by downloader) with probed data
        3. Syncs VFS to update filenames with new metadata

        Note: RTN parsing is done by the downloader, not here.
        Note: Does not handle database commits - caller is responsible for persistence.

        Args:
            item: MediaItem to analyze

        Returns:
            True if analysis succeeded, False if it failed (should retry)
        """
        if not item.filesystem_entry:
            logger.warning(f"No filesystem entry for {item.log_string}, cannot analyze")
            return False

        entry = item.filesystem_entry

        try:
            logger.debug(f"Analyzing media url for {item.log_string}")
            success = self._analyze_with_ffprobe(entry)
            if success:
                logger.debug(f"Media analysis completed for {item.log_string}")
            else:
                logger.warning(f"Media analysis failed for {item.log_string}")
            return success
        except Exception as e:
            logger.error(f"Failed to analyze media url for {item.log_string}: {e}")
            return False

    def _analyze_with_ffprobe(self, entry: MediaEntry) -> bool:
        """
        Analyze media file with ffprobe and update MediaMetadata.

        Args:
            entry: MediaEntry to analyze

        Returns:
            True if metadata was updated, False otherwise
        """
        try:
            log_name = entry.media_item.log_string

            url = getattr(entry, "unrestricted_url", None) or getattr(
                entry, "download_url", None
            )
            ffprobe_metadata = None
            if url:
                try:
                    ffprobe_metadata = parse_media_url(url)
                except Exception as e:
                    # URL probe can fail due to expiration or provider issues
                    logger.debug(f"URL ffprobe failed for {log_name} - {e}")

            if ffprobe_metadata is None:
                return False

            ffprobe_dict = ffprobe_metadata.model_dump(mode="json")
            if entry.media_metadata:
                metadata = MediaMetadata(**entry.media_metadata)
                metadata.update_from_probed_data(ffprobe_dict)
            else:
                logger.warning(
                    f"No existing metadata for {log_name}, creating from probed data only"
                )
                metadata = MediaMetadata(
                    filename=ffprobe_dict.get("filename"), data_source="probed"
                )
                metadata.update_from_probed_data(ffprobe_dict)

            entry.media_metadata = metadata.model_dump(mode="json")
            return True

        except FileNotFoundError:
            logger.warning(
                "VFS file not found for entry %s, cannot analyze",
                getattr(entry, "id", "?"),
            )
            return False
        except Exception:
            logger.error(f"Failed to analyze media entry: {traceback.format_exc()}")
            return False


media_analysis_service = MediaAnalysisService()
