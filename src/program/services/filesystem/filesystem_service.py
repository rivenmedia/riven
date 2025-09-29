"""Filesystem Service for Riven

This service provides a interface for filesystem operations
using the RivenVFS implementation.
"""
from typing import Generator
from loguru import logger

from program.media.item import MediaItem
from program.settings.manager import settings_manager
from program.services.filesystem.path_utils import generate_target_path
from program.services.filesystem.common_utils import get_items_to_update



class FilesystemService:
    """Filesystem service for VFS-only mode"""

    def __init__(self):
        # Service key matches settings category name for reinitialization logic
        self.key = "filesystem"
        # Use filesystem settings
        self.settings = settings_manager.settings.filesystem
        self.riven_vfs = None
        self._initialize_rivenvfs()

    def _initialize_rivenvfs(self):
        """Initialize RivenVFS"""
        try:
            from .vfs import RivenVFS
            from program.services.downloaders import Downloader

            logger.info("Initializing RivenVFS")

            # Get the main downloader service which manages all provider instances
            downloader_service = Downloader()
            if not downloader_service.initialized:
                logger.warning("No downloader services are initialized, RivenVFS will have limited functionality")
                providers = {}
            else:
                # Use the initialized downloader services as providers
                # Map provider names to their corresponding downloader instances
                providers = {}
                for service_class, service_instance in downloader_service.services.items():
                    if service_instance.initialized:
                        # Map service class names to provider keys expected by RivenVFS
                        if 'RealDebrid' in service_class.__name__:
                            providers['realdebrid'] = service_instance
                        elif 'AllDebrid' in service_class.__name__:
                            providers['alldebrid'] = service_instance
                        elif 'TorBox' in service_class.__name__:
                            providers['torbox'] = service_instance

            self.riven_vfs = RivenVFS(
                mountpoint=str(self.settings.mount_path),
                providers=providers,
            )

        except ImportError as e:
            logger.error(f"Failed to import RivenVFS: {e}")
            logger.warning("RivenVFS initialization failed")
        except Exception as e:
            logger.error(f"Failed to initialize RivenVFS: {e}")
            logger.warning("RivenVFS initialization failed")
    
    def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
        """Process a MediaItem using RivenVFS"""
        if not self.riven_vfs:
            logger.error("RivenVFS not initialized")
            yield item
            return

        # Expand parent items (show/season) to leaf items (episodes/movies)
        items_to_process = get_items_to_update(item)
        if not items_to_process:
            logger.debug(f"No items to process for {item.log_string}")
            yield item
            return

        # Process each episode/movie
        for episode_or_movie in items_to_process:
            self._process_single_item(episode_or_movie)

        # Yield the original item for state transition
        yield item

    def _process_single_item(self, item: MediaItem) -> None:
        """Process a single episode or movie item"""
        try:
            # Check if item has filesystem entry
            if not item.filesystem_entry:
                logger.debug(f"No filesystem entry found for {item.log_string}")
                return

            filesystem_entry = item.filesystem_entry

            # Check if already processed (available in VFS)
            if getattr(filesystem_entry, 'available_in_vfs', False):
                logger.debug(f"Item {item.log_string} already processed by FilesystemService")
                return

            # Generate target path using shared logic
            vfs_path = generate_target_path(item, self.settings)

            logger.debug(f"Generated VFS path for {item.log_string}: {vfs_path} (current path: {filesystem_entry.path})")

            # Rename the file from its current path to the VFS path
            if filesystem_entry.path != vfs_path:
                logger.debug(f"Renaming file for {item.log_string}: {filesystem_entry.path} -> {vfs_path}")
                if self.riven_vfs.rename_file(filesystem_entry.path, vfs_path):
                    # Update the in-memory object to match the database
                    filesystem_entry.path = vfs_path
                    filesystem_entry.available_in_vfs = True
                else:
                    logger.error(f"Failed to rename file for {item.log_string}")
                    return
            else:
                # Path is already correct, just mark as available and register with FUSE
                filesystem_entry.available_in_vfs = True
                self.riven_vfs.register_existing_file(vfs_path)

            logger.info(f"Added {item.log_string} to RivenVFS at {vfs_path}")

        except Exception as e:
            logger.error(f"Failed to process {item.log_string} with RivenVFS: {e}")

    def delete_item_files_by_id(self, item_id: str):
        """Delete filesystem entries for an item by ID"""
        self._delete_rivenvfs_files_by_id(item_id)

    def _delete_rivenvfs_files_by_id(self, item_id: str):
        """Delete RivenVFS files associated with a MediaItem by ID (recursively for shows/seasons)."""
        try:
            from program.db.db import db
            from program.media.item import MediaItem
            from program.media.filesystem_entry import FilesystemEntry
            from sqlalchemy import select

            # 1) Gather child IDs (so we can recurse in correct order)
            season_ids: list[str] = []
            episode_ids: list[str] = []
            with db.Session() as session:
                item = session.execute(
                    select(MediaItem).where(MediaItem.id == item_id)
                ).unique().scalar_one_or_none()
                if not item:
                    logger.warning(f"MediaItem with ID {item_id} not found")
                    return

                if item.type == "show":
                    # episodes first, then seasons
                    for season in item.seasons:
                        episode_ids.extend([ep.id for ep in season.episodes])
                        season_ids.append(season.id)
                elif item.type == "season":
                    episode_ids.extend([ep.id for ep in item.episodes])

            # 2) Recurse on children (episodes before seasons)
            for eid in episode_ids:
                self._delete_rivenvfs_files_by_id(eid)
            for sid in season_ids:
                self._delete_rivenvfs_files_by_id(sid)

            # 3) Delete the filesystem entry for the current item
            with db.Session() as session:
                item = session.execute(
                    select(MediaItem).where(MediaItem.id == item_id)
                ).unique().scalar_one_or_none()
                if not item:
                    # It may have been deleted elsewhere already; nothing to do
                    logger.debug(f"MediaItem {item_id} no longer exists; skipping FS deletion")
                    return

                if not item.filesystem_entry_id:
                    logger.debug(f"No filesystem entry associated with item {item_id}")
                    return

                filesystem_entry = session.execute(
                    select(FilesystemEntry).where(FilesystemEntry.id == item.filesystem_entry_id)
                ).unique().scalar_one_or_none()

                if not filesystem_entry:
                    logger.warning(f"FilesystemEntry with ID {item.filesystem_entry_id} not found for item {item_id}")
                    # Clear dangling reference
                    item.filesystem_entry_id = None
                    session.merge(item)
                    session.commit()
                    return

                try:
                    # Clear the filesystem_entry_id from the MediaItem first and commit to release FK
                    path_to_remove = filesystem_entry.path
                    item.filesystem_entry_id = None
                    session.merge(item)
                    session.commit()

                    # Check if any other MediaItems are still referencing this FilesystemEntry
                    other_items = session.execute(
                        select(MediaItem).where(
                            MediaItem.filesystem_entry_id == filesystem_entry.id,
                            MediaItem.id != item_id
                        )
                    ).unique().scalars().all()

                    if not other_items:
                        # No references remain; now remove from VFS/DB and invalidate caches
                        if self.riven_vfs.remove_file(path_to_remove):
                            logger.debug(f"Removed {path_to_remove} from RivenVFS")
                        else:
                            logger.warning(f"Failed to remove {path_to_remove} from RivenVFS")
                    else:
                        logger.debug(
                            f"FilesystemEntry {path_to_remove} still referenced by {len(other_items)} other items; "
                            "skipping VFS removal"
                        )

                    logger.info(f"Removed filesystem entry link for item {getattr(item, 'log_string', item.id)}")

                except Exception as e:
                    session.rollback()
                    logger.error(f"Error removing filesystem entry {getattr(filesystem_entry, 'path', '?')}: {e}")

        except Exception as e:
            logger.error(f"Failed to delete filesystem entry for item {item_id}: {e}")

    def _delete_rivenvfs_files_recursive(self, item: "MediaItem"):
        """Recursively delete RivenVFS files for an item and all its children"""
        from program.media.item import Show, Season

        # Delete files for the current item
        self._delete_rivenvfs_files_by_id(item.id)

        # Recursively delete files for children
        if isinstance(item, Show):
            for season in item.seasons:
                self._delete_rivenvfs_files_recursive(season)
        elif isinstance(item, Season):
            for episode in item.episodes:
                self._delete_rivenvfs_files_recursive(episode)
        # Movies and Episodes are leaf nodes, no children to process

    def close(self):
        """Clean up filesystem resources"""
        try:
            if self.riven_vfs:
                self.riven_vfs.close()
        except Exception as e:
            logger.error(f"Error closing RivenVFS: {e}")
        finally:
            self.riven_vfs = None

    def validate(self) -> bool:
        """Validate service state and configuration.
        Checks that:
        - mount path is set and accessible
        - RivenVFS is initialized and mounted
        """
        try:
            from pathlib import Path
            mount = Path(str(self.settings.mount_path))
            if not str(mount):
                logger.error("FilesystemService: mount_path is empty")
                return False
            # Ensure mount path directory exists
            mount.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"FilesystemService: invalid mount_path '{self.settings.mount_path}': {e}")
            return False

        if not self.riven_vfs:
            logger.error("FilesystemService: RivenVFS not initialized")
            return False

        # RivenVFS maintains an internal mounted flag
        if not getattr(self.riven_vfs, "_mounted", False):
            logger.error("FilesystemService: RivenVFS not mounted")
            return False

        return True

    def reinitialize(self) -> bool:
        """Reinitialize the underlying RivenVFS with current settings."""
        try:
            self.close()
            self._initialize_rivenvfs()
            return self.validate()
        except Exception as e:
            logger.error(f"FilesystemService: reinitialize failed: {e}")
            return False

    @property
    def initialized(self) -> bool:
        """Check if the filesystem service is properly initialized"""
        return self.validate()
