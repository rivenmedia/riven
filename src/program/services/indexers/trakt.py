"""Trakt updater module"""

import time
from datetime import datetime, timedelta
from typing import Generator, Union

from kink import di
from loguru import logger

from program.apis.trakt_api import TraktAPI
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager


class TraktIndexer:
    """Trakt updater class"""
    key = "TraktIndexer"

    def __init__(self):
        self.key = "traktindexer"
        self.ids = []
        self.initialized = True
        self.settings = settings_manager.settings.indexer
        self.failed_ids = set()
        self.api = di[TraktAPI]

    @staticmethod
    def copy_attributes(source, target):
        """Copy attributes from source to target."""
        # Split attributes into safe and lazy-loaded ones
        safe_attributes = ["file", "folder", "update_folder", "symlinked", "is_anime", "symlink_path", "subtitles", "requested_by", "requested_at", "overseerr_id", "active_stream", "requested_id"]
        lazy_attributes = ["streams"]

        # Copy safe attributes
        for attr in safe_attributes:
            target.set(attr, getattr(source, attr, None))

        # Copy lazy-loaded attributes safely
        for attr in lazy_attributes:
            try:
                # Only copy if the source object is attached to a session
                if hasattr(source, '_sa_instance_state') and source._sa_instance_state.session:
                    target.set(attr, getattr(source, attr, None))
                else:
                    # Skip lazy-loaded attributes for detached objects
                    target.set(attr, getattr(source, f'_{attr}', None))
            except Exception:
                # If we can't access the lazy attribute, skip it
                target.set(attr, None)

    def copy_items(self, database_item: MediaItem, api_item: MediaItem):
        """Copy essential attributes from database item to API item without deep nested iteration."""
        logger.debug(f"Copying essential attributes from {database_item.type} to {api_item.type}")

        # Copy essential user/system attributes that should be preserved
        essential_attrs = [
            "file", "folder", "update_folder", "symlinked", "symlink_path",
            "subtitles", "requested_by", "requested_at", "overseerr_id",
            "active_stream", "requested_id"
        ]

        for attr in essential_attrs:
            if hasattr(database_item, attr):
                value = getattr(database_item, attr, None)
                if value is not None:  # Only copy non-None values
                    api_item.set(attr, value)

        # Handle streams safely (lazy-loaded attribute)
        try:
            if hasattr(database_item, '_sa_instance_state') and database_item._sa_instance_state.session:
                # Object is attached to session, safe to access streams
                streams = getattr(database_item, 'streams', None)
                if streams is not None:
                    api_item.set('streams', streams)
            else:
                # Object is detached, try to get cached streams
                cached_streams = getattr(database_item, '_streams', None)
                if cached_streams is not None:
                    api_item.set('streams', cached_streams)
        except Exception as e:
            logger.debug(f"Could not copy streams for {api_item.log_string}: {e}")
            api_item.set('streams', None)

        # Set anime flag (combine both items' anime status)
        is_anime = getattr(database_item, 'is_anime', False) or getattr(api_item, 'is_anime', False)
        api_item.set("is_anime", is_anime)

        logger.debug(f"Successfully copied essential attributes to {api_item.log_string}")
        return api_item

    def run(self, in_item: MediaItem, log_msg: bool = True) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """Run the Trakt indexer for the given item."""
        if not in_item:
            logger.error("Item is None")
            return
        if not (imdb_id := in_item.imdb_id):
            logger.error(f"Item {in_item.log_string} does not have an imdb_id, cannot index it")
            return

        if in_item.imdb_id in self.failed_ids:
            return

        item_type = in_item.type if in_item.type != "mediaitem" else None
        item = self.api.create_item_from_imdb_id(imdb_id, item_type)

        if item:
            if item.type == "show":
                self._add_seasons_to_show(item, imdb_id)
            elif item.type == "movie":
                pass
            else:
                logger.error(f"Indexed IMDb Id {item.imdb_id} returned the wrong item type: {item.type}")
                self.failed_ids.add(in_item.imdb_id)
                return
        else:
            logger.error(f"Failed to index item with imdb_id: {in_item.imdb_id}")
            self.failed_ids.add(in_item.imdb_id)
            return

        item = self.copy_items(in_item, item)
        item.indexed_at = datetime.now()

        if log_msg: # used for mapping symlinks to database, need to hide this log message
            logger.info(f"Indexed IMDb id ({in_item.imdb_id}) as {item.type.title()}: {item.log_string}")

        # Store the item state to ensure database persistence
        item.store_state()

        # Calculate next optimal check time based on show status
        next_check_time = self._calculate_next_check_time(item)

        # Return tuple (item_id, next_check_time) to schedule next run
        if next_check_time:
            yield (item.id, next_check_time)
        else:
            yield item

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        if not item.indexed_at or not item.title:
            return True

        try:
            # Use adaptive intervals instead of fixed interval
            adaptive_interval = TraktIndexer.get_adaptive_update_interval(item)
            return datetime.now() - item.indexed_at > adaptive_interval
        except Exception:
            logger.error(f"Failed to parse date: {item.indexed_at} with adaptive interval")
            return False

    @staticmethod
    def get_adaptive_update_interval(item: MediaItem) -> timedelta:
        """
        Get adaptive update interval based on show characteristics and status.
        Returns appropriate interval for different types of content.
        """
        if item.type != "show":
            # For movies, use standard interval
            settings = settings_manager.settings.indexer
            return timedelta(seconds=settings.update_interval)

        now = datetime.now()

        # Check if show is likely to have new content based on air date patterns
        if TraktIndexer.should_check_for_new_season(item):
            # Shows in potential renewal periods - check every 6 hours
            return timedelta(hours=6)

        # Determine show status based on air dates and metadata
        if item.aired_at:
            days_since_aired = (now - item.aired_at).days

            # Recently aired shows (within last year) - check more frequently
            if days_since_aired <= 365:
                # Very recent shows (within 3 months) - daily checks
                if days_since_aired <= 90:
                    return timedelta(hours=24)
                # Recent shows (3-12 months) - every 2 days
                else:
                    return timedelta(hours=48)

            # Shows that aired 1-3 years ago - weekly checks
            elif days_since_aired <= 1095:  # 3 years
                return timedelta(days=7)

            # Older shows - monthly checks
            else:
                return timedelta(days=30)

        # Shows without air date - assume ongoing, check daily
        return timedelta(hours=24)

    def run_batch_updates(self, items: list[MediaItem], batch_size: int = 10) -> Generator[Union[Movie, Show, Season, Episode], None, None]:
        """
        Run batch updates for multiple items with intelligent rate limiting.
        Processes items in batches to optimize API usage and avoid rate limits.
        """
        if not items:
            return

        # Sort items by priority: ongoing shows first, then by last update time
        prioritized_items = self._prioritize_items_for_batch_update(items)

        # Track shows with new content for summary
        shows_with_new_content = []

        # Process items in batches
        for i in range(0, len(prioritized_items), batch_size):
            batch = prioritized_items[i:i + batch_size]

            logger.debug(f"Processing batch {i//batch_size + 1}/{(len(prioritized_items) + batch_size - 1)//batch_size} with {len(batch)} items")

            # Process each item in the batch with database persistence
            from program.db.db import db
            with db.Session() as session:
                try:
                    for item in batch:
                        try:
                            # Store counts before processing to detect changes
                            old_season_count = getattr(item, 'last_season_count', 0) or 0
                            old_episode_count = getattr(item, 'last_episode_count', 0) or 0

                            # Use the existing run method but with reduced logging
                            for result in self.run(item, log_msg=False):
                                # Merge the updated item back to the database
                                if hasattr(result, 'id'):  # It's an item, not a tuple
                                    session.merge(result)
                                yield result

                            # Check if new content was found
                            new_season_count = getattr(item, 'last_season_count', 0) or 0
                            new_episode_count = getattr(item, 'last_episode_count', 0) or 0

                            if (new_season_count > old_season_count) or (new_episode_count > old_episode_count):
                                shows_with_new_content.append(item.log_string)

                            # Small delay between items to respect rate limits
                            time.sleep(0.1)

                        except Exception as e:
                            logger.error(f"Error processing {item.log_string} in batch: {e}")
                            continue

                    # Commit all changes for this batch
                    session.commit()
                    logger.debug(f"Committed batch {i//batch_size + 1} to database")

                except Exception as e:
                    session.rollback()
                    logger.error(f"Error committing batch {i//batch_size + 1}, rolling back: {e}")

            # Longer delay between batches to avoid overwhelming the API
            if i + batch_size < len(prioritized_items):
                time.sleep(2)  # 2 second delay between batches

        # Summary log message
        if shows_with_new_content:
            logger.log("TRAKT", f"🎉 BATCH COMPLETE: Found new content for {len(shows_with_new_content)} shows out of {len(prioritized_items)} checked")
            logger.info(f"📺 Shows with new content: {', '.join(shows_with_new_content[:5])}{'...' if len(shows_with_new_content) > 5 else ''}")
        else:
            logger.info(f"✅ Batch processing complete: Checked {len(prioritized_items)} shows, no new content found")

        logger.info(f"Completed batch processing of {len(prioritized_items)} items")

    def _prioritize_items_for_batch_update(self, items: list[MediaItem]) -> list[MediaItem]:
        """
        Prioritize items for batch updates based on likelihood of having new content.
        Returns items sorted by priority (highest first).
        """
        def get_priority_score(item: MediaItem) -> int:
            """Calculate priority score for an item (higher = more priority)."""
            score = 0

            # Prioritize shows over movies
            if item.type == "show":
                score += 100

            # Prioritize items that might have new seasons
            if self.should_check_for_new_season(item):
                score += 50

            # Prioritize recently aired content
            if item.aired_at:
                days_since_aired = (datetime.now() - item.aired_at).days
                if days_since_aired <= 90:  # Very recent
                    score += 30
                elif days_since_aired <= 365:  # Recent
                    score += 20
                elif days_since_aired <= 1095:  # Moderately recent
                    score += 10

            # Prioritize items that haven't been checked recently
            if item.indexed_at:
                hours_since_indexed = (datetime.now() - item.indexed_at).total_seconds() / 3600
                if hours_since_indexed > 168:  # More than a week
                    score += 25
                elif hours_since_indexed > 72:  # More than 3 days
                    score += 15
                elif hours_since_indexed > 24:  # More than a day
                    score += 10
            else:
                # Never indexed - highest priority
                score += 100

            return score

        # Sort by priority score (descending)
        return sorted(items, key=get_priority_score, reverse=True)

    @staticmethod
    def get_shows_needing_update(limit: int = 100) -> list[Show]:
        """
        Get shows that need updating based on status tracking and priority.
        Uses memory-efficient database queries instead of loading all shows.
        """
        from program.db.db import db
        from program.media.item import MediaItem
        from sqlalchemy import select, func
        from datetime import datetime, timedelta

        shows_needing_update = []

        with db.Session() as session:
            # First, get total count for logging (lightweight query)
            total_shows = session.execute(
                select(func.count(MediaItem.id)).where(MediaItem.type == "show")
            ).scalar_one()

            logger.debug(f"Checking {total_shows} shows for updates (memory-efficient)")

            # Memory-efficient approach: Query shows that likely need updates
            # Priority 1: Shows that haven't been indexed recently
            recent_threshold = datetime.now() - timedelta(hours=6)

            # Build query for shows that need updating (without loading full objects)
            base_query = (
                select(MediaItem.id, MediaItem.indexed_at, MediaItem.last_state, MediaItem.aired_at)
                .where(MediaItem.type == "show")
            )

            # Get shows in batches to avoid memory issues
            batch_size = 500  # Process 500 shows at a time
            offset = 0
            found_count = 0

            while found_count < limit:
                # Get batch of show metadata (not full objects)
                batch_query = base_query.offset(offset).limit(batch_size)
                show_metadata = session.execute(batch_query).all()

                if not show_metadata:
                    break  # No more shows to process

                # Filter shows that need updating based on metadata
                candidate_ids = []
                for show_id, indexed_at, last_state, aired_at in show_metadata:
                    # Quick filtering based on metadata only
                    needs_update = False

                    # Never indexed or indexed long ago
                    if not indexed_at or indexed_at < recent_threshold:
                        needs_update = True
                    # Ongoing shows that might have new episodes
                    elif last_state in ['Ongoing', 'PartiallyCompleted'] and aired_at:
                        needs_update = True

                    if needs_update:
                        candidate_ids.append(show_id)
                        found_count += 1
                        if found_count >= limit:
                            break

                # Only load full objects for shows that actually need updating
                if candidate_ids:
                    shows_batch = session.execute(
                        select(MediaItem)
                        .where(MediaItem.id.in_(candidate_ids))
                        .limit(min(len(candidate_ids), limit - len(shows_needing_update)))
                    ).unique().scalars().all()

                    # Final filtering with full object access
                    for show in shows_batch:
                        if TraktIndexer.should_submit(show):
                            shows_needing_update.append(show)
                            # Expunge to free memory immediately
                            session.expunge(show)

                        if len(shows_needing_update) >= limit:
                            break

                offset += batch_size

                # Safety break to avoid infinite loops
                if offset > total_shows:
                    break

            logger.info(f"Found {len(shows_needing_update)} shows needing updates (checked {min(offset, total_shows)} shows)")
            return shows_needing_update

    def update_shows_batch(self, limit: int = 50, batch_size: int = 10) -> int:
        """
        Update shows in batches with intelligent rate limiting.
        Returns the number of shows processed.
        """
        shows = self.get_shows_needing_update(limit)
        if not shows:
            logger.debug("No shows need updating at this time")
            return 0

        processed_count = 0
        for result in self.run_batch_updates(shows, batch_size):
            processed_count += 1

        logger.info(f"Batch update completed: processed {processed_count} items from {len(shows)} shows")
        return len(shows)

    @staticmethod
    def should_check_for_new_season(item: MediaItem) -> bool:
        """
        Check if a show should be checked for new seasons based on air date patterns.
        Returns True if the show is likely to have new content soon.
        """
        if item.type != "show" or not item.aired_at:
            return False

        now = datetime.now()
        air_date = item.aired_at

        # Calculate months since last air date
        months_since_aired = (now.year - air_date.year) * 12 + (now.month - air_date.month)

        # Check for seasonal patterns (shows that typically air annually)
        # Most shows have new seasons 12-18 months after the previous season
        if 10 <= months_since_aired <= 20:
            # Check more frequently during typical renewal periods
            return True

        # Check for shows that might be getting renewed (6-24 months range)
        if 6 <= months_since_aired <= 24:
            # Check if we're in a typical TV season (Fall: Sep-Nov, Spring: Jan-May)
            current_month = now.month
            if current_month in [1, 2, 3, 4, 5, 9, 10, 11]:
                return True

        return False

    @staticmethod
    def has_potential_new_content(item: MediaItem) -> bool:
        """Check if a show might have new content based on various factors."""
        if item.type != "show":
            return False

        # Always check if we've never indexed before
        if not item.indexed_at:
            return True

        # Check if it's been a reasonable time since last check
        settings = settings_manager.settings.indexer
        min_check_interval = timedelta(hours=4)  # Minimum 4 hours between checks

        if datetime.now() - item.indexed_at < min_check_interval:
            return False

        # For shows with recent air dates, check more frequently
        if item.aired_at and item.aired_at > datetime.now() - timedelta(days=365):
            # Recent shows get checked more often
            return datetime.now() - item.indexed_at > timedelta(hours=12)
        else:
            # Older shows get checked less frequently
            return datetime.now() - item.indexed_at > timedelta(days=7)


    def _add_seasons_to_show(self, show: Show, imdb_id: str):
        """Add seasons to the given show using Trakt API with change detection."""
        if not imdb_id or not imdb_id.startswith("tt"):
            logger.error(f"Item {show.log_string} does not have an imdb_id, cannot index it")
            return

        seasons_response = self.api.get_show(imdb_id)

        # Extract seasons list from API response - handle both list and dict responses
        if isinstance(seasons_response, list):
            seasons = seasons_response
        elif isinstance(seasons_response, dict) and seasons_response:
            # If it's a dict, it might be an error response or unexpected format
            logger.warning(f"Unexpected dict response from Trakt API for {show.log_string}: {seasons_response}")
            seasons = []
        else:
            # Handle None or other unexpected types
            seasons = []

        # Extract show status information from API response
        self._extract_and_update_show_status(show, seasons)

        # Count current seasons and episodes from API with null safety
        seasons_list = seasons or []
        current_season_count = len([s for s in seasons_list if hasattr(s, 'number') and s.number > 0])
        current_episode_count = sum(len(getattr(s, 'episodes', None) or []) for s in seasons_list if hasattr(s, 'number') and s.number > 0)

        # Build current episode counts per season
        current_season_episode_counts = {}
        for season in seasons_list:
            if hasattr(season, 'number') and season.number > 0:
                episodes = getattr(season, 'episodes', None) or []
                current_season_episode_counts[str(season.number)] = len(episodes)

        # Get stored counts (default to 0 if not set)
        stored_season_count = getattr(show, 'last_season_count', 0) or 0
        stored_episode_count = getattr(show, 'last_episode_count', 0) or 0
        stored_season_episode_counts = getattr(show, 'season_episode_counts', {}) or {}

        # Debug logging to identify why counts are 0
        raw_season_count = getattr(show, 'last_season_count', 'MISSING')
        raw_episode_count = getattr(show, 'last_episode_count', 'MISSING')
        if stored_season_count == 0 and current_season_count > 0:
            logger.debug(f"🔍 DEBUG: {show.log_string} - raw_season_count={raw_season_count}, stored_season_count={stored_season_count}, current_season_count={current_season_count}")
            logger.debug(f"🔍 DEBUG: {show.log_string} - show.id={show.id}, indexed_at={getattr(show, 'indexed_at', 'MISSING')}")

        # Check if there are new seasons or episodes
        has_new_seasons = current_season_count > stored_season_count
        has_new_episodes = current_episode_count > stored_episode_count

        # Check for new episodes in specific seasons
        new_episodes_in_seasons = []
        for season_num, episode_count in current_season_episode_counts.items():
            stored_count = stored_season_episode_counts.get(season_num, 0)
            if episode_count > stored_count:
                new_episodes_in_seasons.append(f"S{season_num}: {stored_count} -> {episode_count}")

        # Log changes with prominent user-friendly messages
        if has_new_seasons:
            logger.log("TRAKT", f"🆕 NEW SEASON FOUND! {show.log_string} now has {current_season_count} seasons (was {stored_season_count})")
            logger.info(f"📺 {show.log_string}: Season {stored_season_count + 1} to {current_season_count} detected and will be processed")
        elif new_episodes_in_seasons:
            logger.log("TRAKT", f"🆕 NEW EPISODES FOUND! {show.log_string}: {', '.join(new_episodes_in_seasons)}")
            logger.info(f"📺 {show.log_string}: New episodes detected and will be processed")
        elif stored_season_count > 0:  # Skip logging for first-time indexing
            logger.debug(f"✅ No new content for {show.log_string} (S:{current_season_count}, E:{current_episode_count})")

        # Update stored counts
        show.set("last_season_count", current_season_count)
        show.set("last_episode_count", current_episode_count)
        show.set("season_episode_counts", current_season_episode_counts)

        # Process seasons (only new ones if we have existing data)
        for season in seasons or []:
            if not hasattr(season, 'number') or season.number == 0:
                continue
            season_item = self.api.map_item_from_data(season, "season", show.genres)
            if season_item:
                # Safe iteration over episodes with null check
                episodes = getattr(season, 'episodes', None) or []
                for episode in episodes:
                    episode_item = self.api.map_item_from_data(episode, "episode", show.genres)
                    if episode_item:
                        season_item.add_episode(episode_item)
                show.add_season(season_item)

    def _extract_and_update_show_status(self, show: Show, seasons):
        """
        Extract show status information from API data and update the show.
        """
        try:
            # Determine show status based on air dates and patterns
            now = datetime.now()
            last_air_date = None
            next_air_date = None

            # Find the most recent air date from all episodes
            all_episodes = []
            for season in seasons or []:
                if hasattr(season, 'number') and season.number > 0:  # Skip specials
                    episodes = getattr(season, 'episodes', None) or []
                    all_episodes.extend(episodes)

            logger.debug(f"Status extraction for {show.log_string}: Found {len(all_episodes)} total episodes")

            # Sort episodes by air date - use first_aired from raw API data
            aired_episodes = []
            for ep in all_episodes:
                first_aired = getattr(ep, 'first_aired', None)
                if first_aired:
                    try:
                        # Parse the date string to datetime object
                        aired_date = datetime.strptime(first_aired, "%Y-%m-%dT%H:%M:%S.%fZ")
                        aired_episodes.append((ep, aired_date))
                    except (ValueError, TypeError) as e:
                        logger.debug(f"Could not parse air date '{first_aired}' for episode: {e}")
                        continue

            logger.debug(f"Status extraction for {show.log_string}: Found {len(aired_episodes)} episodes with valid air dates")

            if aired_episodes:
                # Sort by air date
                aired_episodes.sort(key=lambda x: x[1])
                last_air_date = aired_episodes[-1][1]  # Get the datetime from tuple
                logger.debug(f"Status extraction for {show.log_string}: Last air date: {last_air_date}")
            else:
                # Debug: Check what's actually in the episodes
                if all_episodes:
                    sample_episode = all_episodes[0]
                    episode_attrs = [attr for attr in dir(sample_episode) if not attr.startswith('_')]
                    logger.debug(f"Status extraction for {show.log_string}: Sample episode attributes: {episode_attrs}")
                    logger.debug(f"Status extraction for {show.log_string}: Sample episode first_aired: {getattr(sample_episode, 'first_aired', 'NOT_FOUND')}")
                else:
                    logger.debug(f"Status extraction for {show.log_string}: No episodes found in any season")

            # Determine show status based on air patterns
            status = "unknown"
            if last_air_date:
                days_since_last_air = (now - last_air_date).days

                if days_since_last_air <= 30:
                    status = "ongoing"  # Recently aired
                elif days_since_last_air <= 365:
                    # Check if there's a regular pattern suggesting ongoing status
                    if len(aired_episodes) >= 2:
                        # Look at recent episode intervals - use datetime from tuple
                        recent_episodes = aired_episodes[-5:] if len(aired_episodes) >= 5 else aired_episodes
                        intervals = []
                        for i in range(1, len(recent_episodes)):
                            # Extract datetime from tuple (ep, aired_date)
                            interval = (recent_episodes[i][1] - recent_episodes[i-1][1]).days
                            intervals.append(interval)

                        if intervals:
                            avg_interval = sum(intervals) / len(intervals)
                            if avg_interval <= 14:  # Weekly or bi-weekly show
                                status = "ongoing" if days_since_last_air <= 60 else "hiatus"
                            else:
                                status = "hiatus"  # Longer gaps suggest hiatus
                    else:
                        status = "hiatus"
                else:
                    status = "ended"  # No recent activity

            # Estimate next air date for ongoing shows
            if status == "ongoing" and len(aired_episodes) >= 2:
                # Use average interval to predict next episode - use datetime from tuple
                recent_episodes = aired_episodes[-3:] if len(aired_episodes) >= 3 else aired_episodes
                if len(recent_episodes) >= 2:
                    intervals = []
                    for i in range(1, len(recent_episodes)):
                        # Extract datetime from tuple (ep, aired_date)
                        interval = (recent_episodes[i][1] - recent_episodes[i-1][1]).days
                        intervals.append(interval)

                    if intervals:
                        avg_interval = sum(intervals) / len(intervals)
                        next_air_date = last_air_date + timedelta(days=int(avg_interval))

            # Update show status
            if hasattr(show, 'update_show_status'):
                show.update_show_status(status, last_air_date, next_air_date)
                logger.debug(f"Updated status for {show.log_string}: {status} (last: {last_air_date}, next: {next_air_date})")

                # Store status info for intelligent scheduling
                show._trakt_status = status
                show._trakt_next_air_date = next_air_date

        except Exception as e:
            logger.error(f"Error extracting show status for {show.log_string}: {e}")

    def _calculate_next_check_time(self, item):
        """
        Calculate the optimal next check time based on show status and predicted air date.
        Returns datetime for when this item should be checked next, or None for default behavior.
        """
        if item.type != "show":
            return None  # Use default scheduling for non-shows

        # Get status info from the show (set during status extraction)
        status = getattr(item, '_trakt_status', 'unknown')
        next_air_date = getattr(item, '_trakt_next_air_date', None)

        now = datetime.now()

        if status == "ongoing" and next_air_date:
            # For ongoing shows with predicted air dates, check a few hours before expected air time
            buffer_hours = 6  # Check 6 hours before predicted air time
            next_check_time = next_air_date - timedelta(hours=buffer_hours)

            # Don't schedule too far in the future (max 30 days)
            if next_check_time > now + timedelta(days=30):
                next_check_time = now + timedelta(days=7)  # Weekly check for distant shows

            # Don't schedule in the past or too soon
            elif next_check_time <= now + timedelta(hours=1):
                next_check_time = now + timedelta(hours=12)  # Check in 12 hours

            logger.debug(f"Intelligent scheduling: {item.log_string} next check at {next_check_time} (ongoing, next air: {next_air_date})")
            return next_check_time

        elif status == "hiatus":
            # For shows on hiatus, check weekly to see if they resume
            next_check_time = now + timedelta(days=7)
            logger.debug(f"Intelligent scheduling: {item.log_string} next check at {next_check_time} (hiatus)")
            return next_check_time

        elif status == "ended":
            # For ended shows, check monthly for potential revivals/reboots
            next_check_time = now + timedelta(days=30)
            logger.debug(f"Intelligent scheduling: {item.log_string} next check at {next_check_time} (ended)")
            return next_check_time

        else:
            # For unknown status, use default adaptive scheduling
            logger.debug(f"Using default scheduling for {item.log_string} (status: {status})")
            return None
