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
from program.utils.ffprobe import probe_media_path
from program.media.models import MediaMetadata

from program.media.item import MediaItem
from program.settings.manager import settings_manager


from program.media.media_entry import MediaEntry


def analyze_entry(entry: MediaEntry) -> bool:
    """Analyze a MediaEntry using the best available source (URL first, then VFS).

    Preference order:
    1) Direct/unrestricted URL (fast, avoids VFS race/rename)
    2) Mounted VFS path (fallback)

    Updates the entry.media_metadata in-place. Returns True on successful probe
    (note: may return True even if values didn't materially change).
    """
    try:
        item = entry.media_item
        log_name = getattr(
            item, "log_string", f"MediaEntry(id={getattr(entry, 'id', '?')})"
        )

        # url probe
        url = getattr(entry, "unrestricted_url", None) or getattr(
            entry, "download_url", None
        )
        ffprobe_metadata = None
        if url:
            try:
                ffprobe_metadata = probe_media_path(url)
            except Exception:
                # URL probe can fail due to expiration or provider issues; fall back to VFS
                logger.debug(
                    f"URL ffprobe failed for {log_name}, falling back to VFS path"
                )

        # file probe fallback
        if ffprobe_metadata is None:
            mount_path = settings_manager.settings.filesystem.mount_path
            vfs_paths = entry.get_all_vfs_paths()
            if not vfs_paths:
                logger.warning(f"No VFS paths for {log_name}, cannot run ffprobe")
                return False

            vfs_path = vfs_paths[0]
            full_path = os.path.join(mount_path, vfs_path.lstrip("/"))

            if not os.path.exists(full_path):
                logger.debug(f"File not found for ffprobe: {full_path}")
                return False

            ffprobe_metadata = probe_media_path(full_path)
            if not ffprobe_metadata:
                logger.warning(f"ffprobe returned no data for {log_name}")
                return False

        ffprobe_dict = ffprobe_metadata.model_dump(mode="json")

        # Update or create MediaMetadata
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

        # Persist back on entry (SQLAlchemy object; caller will commit)
        entry.media_metadata = metadata.model_dump(mode="json")
        logger.debug(f"ffprobe analysis successful for {log_name}")
        return True

    except FileNotFoundError:
        logger.warning(
            "VFS file not found for entry %s, cannot analyze", getattr(entry, "id", "?")
        )
        return False
    except Exception:
        logger.error(f"Failed to analyze media entry: {traceback.format_exc()}")
        return False


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

            # Run ffprobe analysis using entry-centric helper
            metadata_updated = analyze_entry(entry)

            # Sync VFS to update filenames with new metadata (resolution, codec, etc.)
            if metadata_updated:
                from program.program import riven
                from program.services.filesystem import FilesystemService

                filesystem_service = riven.services.get(FilesystemService)
                if filesystem_service and filesystem_service.riven_vfs:
                    filesystem_service.riven_vfs.sync(item)
                    logger.debug(
                        f"VFS synced after media analysis for {item.log_string}"
                    )

            logger.debug(f"Media analysis completed for {item.log_string}")

        except FileNotFoundError:
            logger.warning(f"VFS file not found for {item.log_string}, cannot analyze")
        except Exception as e:
            logger.error(f"Failed to analyze media file for {item.log_string}: {e}")
