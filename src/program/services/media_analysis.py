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

from program.media.item import Episode, MediaItem, Movie
from program.media.models import DataSource, MediaMetadata
from program.utils.ffprobe import parse_media_url
from program.core.analysis_service import AnalysisService
from program.utils.debrid_cdn_url import DebridCDNUrl


class MediaAnalysisService(AnalysisService):
    """Service for analyzing media files and extracting metadata."""

    def __init__(self):
        super().__init__()

        self.initialized = True
        logger.info("Media Analysis service initialized")

    @classmethod
    def get_key(cls) -> str:
        return "media_analysis"

    @property
    def enabled(self) -> bool:
        """Media analysis is always enabled as it's a core service."""
        return True

    def should_submit(self, item: MediaItem) -> bool:
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

        if not isinstance(item, Movie | Episode):
            return False

        if not (media_entry := item.media_entry):
            return False

        if (metadata := media_entry.media_metadata) and metadata.probed_at:
            return False

        return True

    async def run(self, item: MediaItem) -> bool:
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
        """

        if not (media_entry := item.media_entry):
            logger.warning(f"No media entry for {item.log_string}, cannot analyze")

            return False

        validated_url = DebridCDNUrl(media_entry).validate()

        if not validated_url:
            logger.warning(f"No download URL for {item.log_string}, cannot analyze")

            return False

        try:
            logger.debug(f"Analyzing media file for {item.log_string}")

            if self._analyze_with_ffprobe(validated_url, item):
                logger.debug(f"Media analysis completed for {item.log_string}")

                return True
        except FileNotFoundError:
            logger.warning(f"VFS file not found for {item.log_string}, cannot analyze")
        except Exception as e:
            logger.error(f"Failed to analyze media file for {item.log_string}: {e}")

        return False

    def _analyze_with_ffprobe(self, playback_url: str, item: MediaItem) -> bool:
        """
        Analyze media file with ffprobe and update MediaMetadata.

        Args:
            file_path: Full path to the media file
            item: MediaItem being analyzed

        Returns:
            True if metadata was updated, False otherwise
        """

        try:
            if not playback_url:
                logger.debug(
                    f"Download URL not found to run ffprobe with item: {item.log_string}"
                )
                return False

            if ffprobe_metadata := parse_media_url(playback_url):
                media_entry = item.media_entry

                assert media_entry

                # Get or create MediaMetadata
                if media_entry.media_metadata:
                    # Update existing metadata with probed data
                    metadata = media_entry.media_metadata
                    metadata.update_from_probed_data(ffprobe_metadata)
                else:
                    # Create new metadata from probed data only
                    # This shouldn't happen since downloader creates it, but handle it anyway
                    logger.warning(
                        f"No existing metadata for {item.log_string}, creating from probed data only"
                    )

                    metadata = MediaMetadata(
                        filename=ffprobe_metadata.filename,
                        data_source=DataSource.PROBED,
                    )
                    metadata.update_from_probed_data(ffprobe_metadata)

                # Store updated metadata
                media_entry.media_metadata = metadata

                logger.debug(f"ffprobe analysis successful for {item.log_string}")

                return True

            logger.warning(f"ffprobe returned no data for {item.log_string}")

            return False
        except Exception:
            logger.error(
                f"FFprobe analysis failed for {item.log_string}: {traceback.format_exc()}"
            )
            return False


media_analysis_service = MediaAnalysisService()
