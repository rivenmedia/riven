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

import os
import traceback

from loguru import logger
from program.utils.ffprobe import parse_media_file
from program.media.models import MediaMetadata

from program.media.item import MediaItem
from program.settings.manager import settings_manager


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

    def run(self, item: MediaItem):
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
        if not item.filesystem_entry:
            logger.warning(f"No filesystem entry for {item.log_string}, cannot analyze")
            return

        entry = item.filesystem_entry

        try:
            logger.debug(f"Analyzing media file for {item.log_string}")
            # Get the mounted VFS path for ffprobe
            # Note: We use mount_path (host VFS mount) not library_path (container path)
            mount_path = settings_manager.settings.filesystem.mount_path

            # Generate VFS path from entry
            vfs_paths = entry.get_all_vfs_paths()
            if not vfs_paths:
                logger.warning(
                    f"No VFS paths for {item.log_string}, cannot run ffprobe"
                )
                return

            # Use the first (base) path for ffprobe
            vfs_path = vfs_paths[0]
            full_path = os.path.join(mount_path, vfs_path.lstrip("/"))

            # Run ffprobe analysis
            self._analyze_with_ffprobe(full_path, item)

            logger.debug(f"Media analysis completed for {item.log_string}")

        except FileNotFoundError:
            logger.warning(f"VFS file not found for {item.log_string}, cannot analyze")
        except Exception as e:
            logger.error(f"Failed to analyze media file for {item.log_string}: {e}")

    def _analyze_with_ffprobe(self, file_path: str, item: MediaItem) -> bool:
        """
        Analyze media file with ffprobe and update MediaMetadata.

        Args:
            file_path: Full path to the media file
            item: MediaItem being analyzed

        Returns:
            True if metadata was updated, False otherwise
        """
        try:
            if not os.path.exists(file_path):
                logger.debug(f"File not found for ffprobe: {file_path}")
                return False

            ffprobe_metadata = parse_media_file(file_path)
            if ffprobe_metadata:
                ffprobe_dict = ffprobe_metadata.model_dump(mode="json")

                # Get or create MediaMetadata
                if item.filesystem_entry.media_metadata:
                    # Update existing metadata with probed data
                    metadata = MediaMetadata(**item.filesystem_entry.media_metadata)
                    metadata.update_from_probed_data(ffprobe_dict)
                else:
                    # Create new metadata from probed data only
                    # This shouldn't happen since downloader creates it, but handle it anyway
                    logger.warning(
                        f"No existing metadata for {item.log_string}, creating from probed data only"
                    )
                    metadata = MediaMetadata(
                        filename=ffprobe_dict.get("filename"), data_source="probed"
                    )
                    metadata.update_from_probed_data(ffprobe_dict)

                # Store updated metadata
                item.filesystem_entry.media_metadata = metadata.model_dump(mode="json")
                logger.debug(f"ffprobe analysis successful for {item.log_string}")
                return True

            logger.warning(f"ffprobe returned no data for {item.log_string}")
            return False
        except Exception:
            logger.error(
                f"FFprobe analysis failed for {item.log_string}: {traceback.format_exc()}"
            )
            return False
