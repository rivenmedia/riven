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
from datetime import datetime
import traceback
from typing import Optional, Dict, Any

from loguru import logger
from PTT import parse_title
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
        - Item hasn't been analyzed yet (no parsed_data)
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
        
        # Check if already analyzed by looking for parsed_data
        if hasattr(item, 'parsed_data') and item.parsed_data:
            return False
            
        return True

    def run(self, item: MediaItem):
        """
        Analyze media file and store metadata.

        Performs:
        1. FFprobe analysis (video/audio codecs, embedded subtitles)
        2. PTT filename parsing (resolution, codec, audio, release group, etc.)
        3. Stores results in MediaItem.parsed_data for later use

        Note: Does not handle database commits - caller is responsible for persistence.

        Args:
            item: MediaItem to analyze
        """
        if not item.filesystem_entry:
            logger.warning(f"No filesystem entry for {item.log_string}, cannot analyze")
            return

        try:
            logger.debug(f"Analyzing media file for {item.log_string}")

            # Get the mounted VFS path for ffprobe
            mount_path = settings_manager.settings.filesystem.mount_path
            vfs_path = item.filesystem_entry.path
            full_path = os.path.join(mount_path, vfs_path.lstrip('/'))

            # Get original filename for PTT parsing
            original_filename = item.filesystem_entry.original_filename

            # Initialize results dictionary
            analysis_results = {
                'analyzed_at': datetime.now().isoformat(),
                'ffprobe_data': None,
                'parsed_filename': None,
            }

            # 1. Run ffprobe analysis
            ffprobe_data = self._analyze_with_ffprobe(full_path, item)
            if ffprobe_data:
                analysis_results['ffprobe_data'] = ffprobe_data

            # 2. Parse filename with PTT
            if original_filename:
                parsed_data = self._parse_filename(original_filename, item)
                if parsed_data:
                    analysis_results['parsed_filename'] = parsed_data

            # 3. Store results in MediaItem
            if ffprobe_data and parsed_data:
                item.parsed_data = analysis_results

            logger.debug(f"Media analysis completed for {item.log_string}")

        except FileNotFoundError:
            logger.warning(f"VFS file not found for {item.log_string}, cannot analyze")
        except Exception as e:
            logger.error(f"Failed to analyze media file for {item.log_string}: {e}")

    def _analyze_with_ffprobe(self, file_path: str, item: MediaItem) -> Dict[str, Any]:
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
                return None

            media_metadata = parse_media_file(file_path)
            if media_metadata:
                ffprobe_dict = media_metadata.model_dump_json()
                logger.debug(f"FFprobe analysis successful for {item.log_string}")
                return ffprobe_dict

            logger.warning(f"FFprobe returned no data for {item.log_string}")
            return {}
        except Exception:
            logger.error(f"FFprobe analysis failed for {item.log_string}: {traceback.format_exc()}")
            return {}

    def _parse_filename(self, filename: str, item: MediaItem) -> Dict[str, Any]:
        """
        Parse filename with PTT to extract metadata.
        
        Args:
            filename: Original filename to parse
            item: MediaItem being analyzed
            
        Returns:
            Dictionary with parsed metadata or None if parsing fails
        """
        try:
            parsed_data = parse_title(filename)
            if parsed_data:
                logger.debug(f"PTT parsed {len(parsed_data)} fields from filename for {item.log_string}")
                return parsed_data

            logger.warning(f"PTT returned no data for filename: {filename}")
            return {}
        except Exception:
            logger.error(f"PTT parsing failed for {item.log_string}: {traceback.format_exc()}")
            return {}
