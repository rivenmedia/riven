"""
Service for creating MediaEntry objects for scraped items.

This service creates MediaEntry objects for each active scraping profile
and yields them so they can be processed through run_thread_with_db_item.
"""

from program.media.item import MediaItem
from program.media.media_entry import MediaEntry
from program.media.entry_state import EntryState
from program.utils.logging import logger


class EntryCreator:
    """
    Service that creates MediaEntry objects for scraped MediaItems.

    After scraping completes, this service:
    1. Expands parent items (shows/seasons) to leaf items (episodes/movies)
    2. Creates MediaEntry objects for each active scraping profile
    3. Yields the entries so they get saved to the database
    4. Entries are then enqueued for download
    """

    def __init__(self):
        self.initialized = True

    def run(self, item: MediaItem):
        """
        Create MediaEntry objects for a scraped MediaItem.

        Handles all MediaItem types:
        - Shows: Expands to episodes
        - Seasons: Expands to episodes
        - Movies: Creates entries directly
        - Episodes: Creates entries directly

        Args:
            item: The MediaItem that was just scraped

        Yields:
            MediaEntry: Each newly created MediaEntry (will be saved by run_thread_with_db_item)
        """
        # Expand parent items (show/season) to leaf items (episodes/movies)
        items_to_process = self._get_items_to_process(item)

        if not items_to_process:
            logger.debug(f"No items to process for {item.log_string}")
            return

        # Process each leaf item (episode or movie)
        total_entries = 0
        for leaf_item in items_to_process:
            # Only Movies and Episodes get MediaEntries (they have actual files)
            if leaf_item.type not in ["movie", "episode"]:
                logger.debug(f"Skipping MediaEntry creation for {leaf_item.log_string}: {leaf_item.type} items don't download")
                continue

            # Create MediaEntry objects for each active scraping profile
            if not self._ensure_profile_entries(leaf_item):
                logger.error(f"Failed to create MediaEntries for {leaf_item.log_string}")
                continue

            # Get only MediaEntry objects in Pending state (newly created or ready to retry)
            # This avoids re-enqueueing entries that are already Downloaded/Available/Completed
            media_entries = [
                e for e in leaf_item.filesystem_entries
                if isinstance(e, MediaEntry) and e.state == EntryState.Pending
            ]

            if not media_entries:
                logger.debug(f"No pending MediaEntries for {leaf_item.log_string} - all profiles already processed or no profiles configured")
                continue

            logger.debug(f"Created {len(media_entries)} pending MediaEntries for {leaf_item.log_string}")
            total_entries += len(media_entries)

            # Yield each entry so it gets saved to the database
            for entry in media_entries:
                yield entry

        if total_entries > 0:
            logger.info(f"EntryCreator created {total_entries} MediaEntries for {item.log_string}")

    def _ensure_profile_entries(self, item: MediaItem) -> bool:
        """
        Ensure MediaEntry objects exist for all configured scraping profiles.

        Creates MediaEntry objects in Pending state for each profile that doesn't
        already have an entry for this item.

        Args:
            item: The MediaItem to create entries for (must be movie or episode)

        Returns:
            bool: True if entries were created or already exist, False on error
        """
        from program.settings.manager import settings_manager

        try:
            # Get expected profiles from settings
            scraping_profiles = getattr(settings_manager.settings, 'scraping_profiles', [])
            if not scraping_profiles:
                return True  # No profiles configured

            # Get existing MediaEntry profiles
            existing_entries = [e for e in item.filesystem_entries if isinstance(e, MediaEntry)]
            existing_profiles = {entry.scraping_profile_name for entry in existing_entries}

            # Create missing MediaEntry objects
            created_count = 0
            for profile in scraping_profiles:
                if profile.name not in existing_profiles:
                    # Create a pending MediaEntry for this profile
                    # NOTE: SQLAlchemy's back_populates automatically adds the entry to item.filesystem_entries
                    # when we set media_item=item, so we don't need to manually append!
                    MediaEntry(
                        media_item=item,
                        scraping_profile_name=profile.name,
                        failed=False
                        # Other fields will be populated by downloader when stream is selected
                    )
                    created_count += 1
                    logger.debug(f"Created MediaEntry for profile '{profile.name}' on {item.log_string}")
                else:
                    logger.debug(f"Skipping profile '{profile.name}' - already has MediaEntry on {item.log_string}")

            if created_count > 0:
                logger.debug(f"Created {created_count} pending MediaEntry objects for {item.log_string}")

            return True

        except Exception as e:
            logger.error(f"Failed to ensure profile entries for {item.log_string}: {e}")
            return False

    def _get_items_to_process(self, item: MediaItem) -> list[MediaItem]:
        """
        Expand parent items (shows/seasons) to leaf items (episodes/movies).

        Args:
            item: MediaItem to expand

        Returns:
            List of leaf MediaItems (episodes or movies)
        """
        if item.type == "show":
            # Expand show to all episodes across all seasons
            episodes = []
            for season in item.seasons:
                episodes.extend(season.episodes)
            return episodes
        elif item.type == "season":
            # Expand season to all episodes
            return list(item.episodes)
        elif item.type in ["movie", "episode"]:
            # Leaf items - return as-is
            return [item]
        else:
            logger.warning(f"Unknown item type: {item.type}")
            return []

