"""
Media Analysis Service for Riven.

Analyzes media files using ffprobe to extract:
- Video/audio codec information
- Embedded subtitle tracks

This service runs once per entry before subtitle fetching to populate
metadata that can be used for intelligent subtitle selection.

Note: Filename parsing is handled by the downloader (RTN), not here.
"""

import os
from datetime import datetime
from typing import Optional

from loguru import logger
from RTN import parse_media_file
from RTN.file_parser import MediaMetadata

from program.settings.manager import settings_manager
from program.media.parsed_media_data import ParsedMediaData, ParsedFilenameData


class MediaAnalysisService:
    """
    Service for analyzing media files and extracting metadata.

    Uses ffprobe (via RTN's parse_media_file) to extract:
    - Video codec information
    - Audio codec information
    - Embedded subtitle tracks

    This service always runs (cannot be disabled) as it provides core
    metadata used by other services like SubtitleService.

    Attributes:
        key: Service identifier ("media_analysis").
        initialized: Always True (service always available).
    """

    def __init__(self):
        """Initialize the MediaAnalysisService."""
        self.key = "media_analysis"
        self.initialized = True
        logger.info("Media Analysis service initialized")

    @property
    def enabled(self) -> bool:
        """
        Check if media analysis is enabled.

        Returns:
            bool: Always True (core service, cannot be disabled).
        """
        return True

    def run(self, entry):
        """
        Analyze a single MediaEntry and store metadata.

        Performs:
        1. FFprobe analysis (video/audio codecs, embedded subtitles)
        2. Uses pre-parsed filename data from downloader (RTN)

        Note: Does not handle database commits - caller is responsible for persistence.

        Args:
            entry: MediaEntry to analyze
        """

        mount_path = settings_manager.settings.filesystem.mount_path

        try:
            logger.debug(f"Analyzing media file for {entry.log_string}")

            # Get the mounted VFS path for ffprobe
            vfs_path = entry.path
            full_path = os.path.join(mount_path, vfs_path.lstrip('/'))

            ffprobe_data = self._analyze_with_ffprobe(full_path, entry)
            if ffprobe_data:
                entry.probed = ffprobe_data

        except FileNotFoundError:
            logger.warning(f"VFS file not found for {entry.log_string}, cannot analyze")
        except Exception as e:
            logger.error(f"Failed to analyze media file for {entry.log_string}: {e}")

    def _analyze_with_ffprobe(self, file_path: str, entry) -> Optional[MediaMetadata]:
        """
        Analyze media file with ffprobe.

        Args:
            file_path: Full path to the media file
            entry: MediaEntry being analyzed

        Returns:
            MediaMetadata model with ffprobe data or None if analysis fails
        """
        try:
            if not os.path.exists(file_path):
                logger.debug(f"File not found for ffprobe: {file_path}")
                return None

            # Use RTN's parse_media_file which wraps ffprobe
            # Returns a MediaMetadata Pydantic model
            media_metadata = parse_media_file(file_path)

            if media_metadata:
                logger.debug(f"FFprobe analysis successful for {entry.log_string}")
                return media_metadata  # Return the model directly
            else:
                logger.warning(f"FFprobe returned no data for {entry.log_string}")
                return None

        except Exception as e:
            logger.error(f"FFprobe analysis failed for {entry.log_string}: {e}")
            return None
