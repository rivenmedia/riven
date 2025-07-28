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
        attributes = ["file", "folder", "update_folder", "symlinked", "is_anime", "symlink_path", "subtitles", "requested_by", "requested_at", "overseerr_id", "active_stream", "requested_id", "streams"]
        for attr in attributes:
            target.set(attr, getattr(source, attr, None))

    def copy_items(self, itema: MediaItem, itemb: MediaItem):
        """Copy attributes from itema to itemb recursively."""
        is_anime = itema.is_anime or itemb.is_anime
        if itema.type == "mediaitem" and itemb.type == "show":
            itema.seasons = itemb.seasons
        if itemb.type == "show" and itema.type != "movie":
            for seasona in itema.seasons:
                for seasonb in itemb.seasons:
                    if seasona.number == seasonb.number:  # Check if seasons match
                        for episodea in seasona.episodes:
                            for episodeb in seasonb.episodes:
                                if episodea.number == episodeb.number:  # Check if episodes match
                                    self.copy_attributes(episodea, episodeb)
                                    episodeb.set("is_anime", is_anime)
                        seasonb.set("is_anime", is_anime)
            itemb.set("is_anime", is_anime)
        elif itemb.type == "movie":
            self.copy_attributes(itema, itemb)
            itemb.set("is_anime", is_anime)
        else:
            logger.error(f"Item types {itema.type} and {itemb.type} do not match cant copy metadata")
        return itemb

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

        # Process items in batches
        for i in range(0, len(prioritized_items), batch_size):
            batch = prioritized_items[i:i + batch_size]

            logger.debug(f"Processing batch {i//batch_size + 1}/{(len(prioritized_items) + batch_size - 1)//batch_size} with {len(batch)} items")

            # Process each item in the batch
            for item in batch:
                try:
                    # Use the existing run method but with reduced logging
                    for result in self.run(item, log_msg=False):
                        yield result

                    # Small delay between items to respect rate limits
                    time.sleep(0.1)

                except Exception as e:
                    logger.error(f"Error processing {item.log_string} in batch: {e}")
                    continue

            # Longer delay between batches to avoid overwhelming the API
            if i + batch_size < len(prioritized_items):
                time.sleep(2)  # 2 second delay between batches

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
        Returns shows sorted by update priority.
        """
        from program.db import db_functions

        # Get all shows from database
        shows = db_functions.get_items_by_ids(
            ids=[],  # Get all items
            item_types=["show"]
        )

        # Filter shows that need updating using status-aware logic
        shows_needing_update = []
        for show in shows:
            # Use new status-aware checking if available, fallback to old logic
            if hasattr(show, 'should_check_for_updates') and show.should_check_for_updates():
                shows_needing_update.append(show)
            elif TraktIndexer.should_submit(show):
                shows_needing_update.append(show)

        # Sort by priority (highest first)
        shows_needing_update.sort(
            key=lambda show: show.get_expected_update_priority() if hasattr(show, 'get_expected_update_priority') else 0,
            reverse=True
        )

        # Limit the number of shows to process
        if len(shows_needing_update) > limit:
            shows_needing_update = shows_needing_update[:limit]

        logger.info(f"Found {len(shows_needing_update)} shows needing updates (status-aware)")
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

        seasons = self.api.get_show(imdb_id)

        # Extract show status information from API response
        self._extract_and_update_show_status(show, seasons)

        # Count current seasons and episodes from API
        current_season_count = len([s for s in seasons if s.number > 0])
        current_episode_count = sum(len(s.episodes) for s in seasons if s.number > 0)

        # Build current episode counts per season
        current_season_episode_counts = {}
        for season in seasons:
            if season.number > 0:
                current_season_episode_counts[str(season.number)] = len(season.episodes)

        # Get stored counts (default to 0 if not set)
        stored_season_count = getattr(show, 'last_season_count', 0) or 0
        stored_episode_count = getattr(show, 'last_episode_count', 0) or 0
        stored_season_episode_counts = getattr(show, 'season_episode_counts', {}) or {}

        # Check if there are new seasons or episodes
        has_new_seasons = current_season_count > stored_season_count
        has_new_episodes = current_episode_count > stored_episode_count

        # Check for new episodes in specific seasons
        new_episodes_in_seasons = []
        for season_num, episode_count in current_season_episode_counts.items():
            stored_count = stored_season_episode_counts.get(season_num, 0)
            if episode_count > stored_count:
                new_episodes_in_seasons.append(f"S{season_num}: {stored_count} -> {episode_count}")

        # Log changes
        if has_new_seasons:
            logger.info(f"New seasons detected for {show.log_string}: {stored_season_count} -> {current_season_count}")
        elif new_episodes_in_seasons:
            logger.info(f"New episodes detected for {show.log_string}: {', '.join(new_episodes_in_seasons)}")
        elif stored_season_count > 0:  # Skip logging for first-time indexing
            logger.debug(f"No new content for {show.log_string} (S:{current_season_count}, E:{current_episode_count})")

        # Update stored counts
        show.set("last_season_count", current_season_count)
        show.set("last_episode_count", current_episode_count)
        show.set("season_episode_counts", current_season_episode_counts)

        # Process seasons (only new ones if we have existing data)
        for season in seasons:
            if season.number == 0:
                continue
            season_item = self.api.map_item_from_data(season, "season", show.genres)
            if season_item:
                for episode in season.episodes:
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
            for season in seasons:
                if season.number > 0:  # Skip specials
                    all_episodes.extend(season.episodes)

            # Sort episodes by air date
            aired_episodes = [ep for ep in all_episodes if hasattr(ep, 'aired_at') and ep.aired_at]
            if aired_episodes:
                aired_episodes.sort(key=lambda ep: ep.aired_at)
                last_air_date = aired_episodes[-1].aired_at

            # Determine show status based on air patterns
            status = "unknown"
            if last_air_date:
                days_since_last_air = (now - last_air_date).days

                if days_since_last_air <= 30:
                    status = "ongoing"  # Recently aired
                elif days_since_last_air <= 365:
                    # Check if there's a regular pattern suggesting ongoing status
                    if len(aired_episodes) >= 2:
                        # Look at recent episode intervals
                        recent_episodes = aired_episodes[-5:] if len(aired_episodes) >= 5 else aired_episodes
                        intervals = []
                        for i in range(1, len(recent_episodes)):
                            interval = (recent_episodes[i].aired_at - recent_episodes[i-1].aired_at).days
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
                # Use average interval to predict next episode
                recent_episodes = aired_episodes[-3:] if len(aired_episodes) >= 3 else aired_episodes
                if len(recent_episodes) >= 2:
                    intervals = []
                    for i in range(1, len(recent_episodes)):
                        interval = (recent_episodes[i].aired_at - recent_episodes[i-1].aired_at).days
                        intervals.append(interval)

                    if intervals:
                        avg_interval = sum(intervals) / len(intervals)
                        next_air_date = last_air_date + timedelta(days=int(avg_interval))

            # Update show status
            if hasattr(show, 'update_show_status'):
                show.update_show_status(status, last_air_date, next_air_date)
                logger.debug(f"Updated status for {show.log_string}: {status} (last: {last_air_date}, next: {next_air_date})")

        except Exception as e:
            logger.error(f"Error extracting show status for {show.log_string}: {e}")
