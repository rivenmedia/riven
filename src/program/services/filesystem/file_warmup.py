"""
Lightweight file warmup service for validating VFS accessibility.

This service performs a minimal stat check (like ls -la) on media files to:
1. Verify debrid links are still accessible
2. Force VFS to unrestrict links (catching dead torrents early)
3. Warm VFS cache for media servers
4. Avoid expensive ffprobe analysis before notifications

Extremely fast since it only stats the file (gets metadata) without reading
any actual file content.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from loguru import logger
from program.media.item import MediaItem
from program.settings.manager import settings_manager


class FileWarmupService:
    """
    Service to warm up VFS files and validate link accessibility.

    Performs minimal stat operations (like ls -la) to ensure files are accessible
    before notifying media servers. Much faster than reading file contents.
    """

    # Maximum concurrent file checks
    MAX_WORKERS = 10

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        """
        Determine if item should be warmed up.

        Args:
            item: MediaItem to check

        Returns:
            True if warmup should run, False otherwise
        """
        if item.type not in ["movie", "episode"]:
            return False

        if not item.filesystem_entry:
            return False

        return True

    def run(self, item: MediaItem) -> bool:
        """
        Warm up file(s) for the given item.

        Performs lightweight stat check (like ls -la) to validate VFS accessibility.
        For episodes, only warms the specific episode.
        For shows/seasons, caller should iterate episodes.

        Args:
            item: MediaItem to warm up

        Returns:
            True if warmup successful, False if file(s) inaccessible

        Raises:
            Exception if VFS errors indicate dead link
        """
        if not item.filesystem_entry:
            logger.warning(f"No filesystem entry for {item.log_string}, cannot warm up")
            return False

        entry = item.filesystem_entry

        try:
            # Get the mounted VFS path
            mount_path = settings_manager.settings.filesystem.mount_path

            # Generate VFS paths from entry
            vfs_paths = entry.get_all_vfs_paths()
            if not vfs_paths:
                logger.warning(
                    f"No VFS paths for {item.log_string}, cannot warm up"
                )
                return False

            # Warm up the primary file
            vfs_path = vfs_paths[0]
            full_path = os.path.join(mount_path, vfs_path.lstrip("/"))

            success = self._warm_single_file(full_path, item)

            if success:
                logger.debug(f"File warmup successful for {item.log_string}")
            else:
                logger.error(f"File warmup failed for {item.log_string}")

            return success

        except FileNotFoundError:
            logger.warning(f"VFS file not found for {item.log_string}")
            return False
        except Exception as e:
            logger.error(f"Failed to warm up file for {item.log_string}: {e}")
            # Re-raise to let caller handle (may need to reset item)
            raise

    def warm_multiple(self, items: list[MediaItem]) -> dict[MediaItem, bool]:
        """
        Warm up multiple files in parallel.

        Useful for shows/seasons with many episodes.

        Args:
            items: List of MediaItems to warm up

        Returns:
            Dictionary mapping items to success status
        """
        results = {}
        mount_path = settings_manager.settings.filesystem.mount_path

        # Prepare tasks
        tasks = []
        for item in items:
            if not self.should_submit(item):
                results[item] = False
                continue

            entry = item.filesystem_entry
            vfs_paths = entry.get_all_vfs_paths()
            if not vfs_paths:
                results[item] = False
                continue

            vfs_path = vfs_paths[0]
            full_path = os.path.join(mount_path, vfs_path.lstrip("/"))
            tasks.append((item, full_path))

        # Warm files in parallel
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            future_to_item = {
                executor.submit(self._warm_single_file, path, item): item
                for item, path in tasks
            }

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    results[item] = future.result()
                except Exception as e:
                    logger.error(f"Warmup failed for {item.log_string}: {e}")
                    results[item] = False

        return results

    def _warm_single_file(self, file_path: str, item: MediaItem) -> bool:
        """
        Perform warmup check on a single file using stat (like ls -la).

        This minimal check forces VFS to unrestrict the link without reading
        any file contents. Much faster than reading data.

        Args:
            file_path: Full path to file
            item: MediaItem (for logging)

        Returns:
            True if file is accessible, False otherwise
        """
        try:
            # Just stat the file (like ls -la does)
            # This will:
            # 1. Force VFS to unrestrict the link
            # 2. Catch dead/expired debrid links
            # 3. Be extremely fast (no data read)
            file_stat = os.stat(file_path)

            # Verify file has size
            if file_stat.st_size == 0:
                logger.warning(f"File is empty: {file_path}")
                return False

            logger.debug(
                f"File warmup OK: {item.log_string} "
                f"({file_stat.st_size / (1024*1024*1024):.2f}GB)"
            )
            return True

        except FileNotFoundError:
            logger.debug(f"File not found for warmup: {file_path}")
            return False
        except OSError as e:
            # OS errors typically indicate VFS/link issues
            logger.error(f"OS error checking file {file_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking file {file_path}: {e}")
            return False
