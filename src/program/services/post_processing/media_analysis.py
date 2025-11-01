"""
Media Analysis Service for Riven.

Analyzes media files using ffprobe and PTT to extract:
- Video/audio codec information
- Embedded subtitle tracks
- Parsed metadata from filename (resolution, codec, audio, etc.)

This service runs once per item before subtitle fetching to populate
metadata that can be used for intelligent subtitle selection and
upgrade decisions.
"""

import os
import traceback

from typing import Any

from loguru import logger
from program.utils.ffprobe import parse_media_file

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
        - Entry hasn't been probed yet (no probed_data in MediaEntry)
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

        # Skip if already probed
        if item.filesystem_entry.probed_data:
            return False

        return True

    def run(self, item: MediaItem):
        """
        Analyze media file and store metadata.

        Performs:
        1. PTT filename parsing (resolution, codec, audio, release group, etc.) - only if not already parsed
        2. FFprobe analysis (video/audio codecs, embedded subtitles) - only if not already probed
        3. Stores PTT results in MediaEntry.parsed_data
        4. Stores ffprobe results in MediaEntry.probed_data

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

            # Get original filename for PTT parsing
            original_filename = entry.original_filename

            # 1. Parse filename with PTT (skip if already parsed by downloader)
            if not entry.parsed_data and original_filename:
                from RTN import parse

                try:
                    parsed = parse(original_filename)
                    if parsed:
                        entry.parsed_data = parsed.model_dump()
                        logger.debug(f"Parsed filename for {item.log_string}")
                except Exception as e:
                    logger.warning(
                        f"Failed to parse filename for {item.log_string}: {e}"
                    )

            # 2. Run ffprobe analysis (skip if already probed)
            if not entry.probed_data:
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
                ffprobe_data = self._analyze_with_ffprobe(full_path, item)

                # Store ffprobe results if we got any
                if ffprobe_data:
                    logger.debug(f"FFprobe analysis completed for {item.log_string}")

            logger.debug(f"Media analysis completed for {item.log_string}")

        except FileNotFoundError:
            logger.warning(f"VFS file not found for {item.log_string}, cannot analyze")
        except Exception as e:
            logger.error(f"Failed to analyze media file for {item.log_string}: {e}")

    def _analyze_with_ffprobe(self, file_path: str, item: MediaItem) -> dict[str, Any]:
        """
        Analyze media file with ffprobe.

        Args:
            file_path: Full path to the media file
            item: MediaItem being analyzed

        Returns:
            Dictionary with ffprobe data or None if analysis fails
        """
        try:
            if not os.path.exists(file_path):
                logger.debug(f"File not found for ffprobe: {file_path}")
                return {}

            media_metadata = parse_media_file(file_path)
            if media_metadata:
                ffprobe_dict = media_metadata.model_dump(mode="json")

                # Store ffprobe data in filesystem_entry.probed_data
                if item.filesystem_entry:
                    item.filesystem_entry.probed_data = ffprobe_dict

                logger.debug(f"ffprobe analysis successful for {item.log_string}")
                return ffprobe_dict

            logger.warning(f"ffprobe returned no data for {item.log_string}")
            return {}
        except Exception:
            logger.error(
                f"FFprobe analysis failed for {item.log_string}: {traceback.format_exc()}"
            )
            return {}
