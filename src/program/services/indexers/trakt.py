"""Trakt updater module"""

from datetime import datetime, timedelta, timezone
import time
from typing import Generator, Optional, Union
from kink import di
from loguru import logger
from tzlocal import get_localzone

from program.apis.trakt_api import TraktAPI
from program.apis.tvmaze_api import TVMazeAPI
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
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
        self.tvmaze_api = di[TVMazeAPI]
        
        # Get the system's local timezone
        try:
            self.local_tz = get_localzone()
        except Exception:
            self.local_tz = timezone.utc
            logger.warning("Could not determine system timezone, using UTC")

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
            logger.debug(f"Indexed IMDb id ({in_item.imdb_id}) as {item.type.title()}: {item.log_string}")
        yield item

    @staticmethod
    def should_submit(item: MediaItem) -> bool:
        if not item.indexed_at or not item.title:
            return True

        settings = settings_manager.settings.indexer

        try:
            interval = timedelta(seconds=settings.update_interval)
            return datetime.now() - item.indexed_at > interval
        except Exception:
            logger.error(f"Failed to parse date: {item.indexed_at} with format: {interval}")
            return False

    def _add_seasons_to_show(self, show: Show, imdb_id: str):
        """Add seasons to the given show using Trakt API."""
        if not imdb_id or not imdb_id.startswith("tt"):
            logger.error(f"Item {show.log_string} does not have an imdb_id, cannot index it")
            return

        seasons = self.api.get_show(imdb_id)
        for season in seasons:
            if season.number == 0:
                continue
            season_item = self.api.map_item_from_data(season, "season", show.genres)
            if season_item:
                # Set season's parent to show
                season_item.parent = show
                
                # Ensure season has timezone-aware dates
                if season_item.aired_at and season_item.aired_at.tzinfo is None:
                    season_item.aired_at = season_item.aired_at.replace(tzinfo=self.local_tz)
                
                for episode in season.episodes:
                    episode_item = self.api.map_item_from_data(episode, "episode", show.genres)
                    if episode_item:
                        # Set episode's parent to season
                        episode_item.parent = season_item
                        
                        # Ensure episode has timezone-aware dates
                        if episode_item.aired_at and episode_item.aired_at.tzinfo is None:
                            episode_item.aired_at = episode_item.aired_at.replace(tzinfo=self.local_tz)
                        
                        season_item.episodes.append(episode_item)
                show.seasons.append(season_item)

    def update_release_times(self, show: Show) -> None:
        """Update release times for a show by comparing Trakt and TVMaze times."""
        # Skip if show is already fully processed
        if show.last_state in [States.Completed, States.Indexed]:
            return

        for season in show.seasons:
            # Skip if season is already fully processed
            if season.last_state in [States.Completed, States.Indexed]:
                continue

            # Track if we've hit a missing episode or future episode in TVMaze
            skip_remaining = False
            season_exists = False  # Track if the season exists in TVMaze
            
            for episode in season.episodes:
                # Skip if episode is already fully processed
                if episode.last_state in [States.Completed, States.Indexed]:
                    continue

                # Skip remaining episodes in season if we already found a reason to skip
                if skip_remaining:
                    break

                # Safe logging with fallback for missing attributes
                log_id = f"{show.title} S{season.number}E{episode.number}"
                logger.debug(f"Processing {log_id}")
                
                # Ensure Trakt time is timezone-aware
                trakt_time = episode.aired_at
                if trakt_time and trakt_time.tzinfo is None:
                    trakt_time = trakt_time.replace(tzinfo=datetime.now().astimezone().tzinfo)
                    episode.aired_at = trakt_time
        
                logger.debug(f"Trakt time for {log_id}: {trakt_time}")
                
                # Get release time from TVMaze and use it if it's earlier or if Trakt has no time
                tvmaze_result = self.tvmaze_api.get_episode_release_time(episode)
                
                # Handle different TVMaze response types
                if isinstance(tvmaze_result, datetime):
                    # Got a valid air date
                    season_exists = True
                    tvmaze_time = tvmaze_result
                    
                    # Ensure TVMaze time is timezone-aware
                    if tvmaze_time.tzinfo is None:
                        tvmaze_time = tvmaze_time.replace(tzinfo=datetime.now().astimezone().tzinfo)
                    
                    logger.debug(f"TVMaze time for {log_id}: {tvmaze_time}")
                    if not trakt_time:
                        logger.debug(f"Using TVMaze time (no Trakt time available)")
                        episode.aired_at = tvmaze_time
                    elif tvmaze_time < trakt_time:
                        logger.debug(f"Using TVMaze time (earlier than Trakt: {tvmaze_time} vs {trakt_time})")
                        episode.aired_at = tvmaze_time
                    else:
                        logger.debug(f"Using Trakt time (earlier than TVMaze: {trakt_time} vs {tvmaze_time})")
                elif tvmaze_result is False:
                    # Episode exists but has no air date
                    season_exists = True
                    if not trakt_time:
                        logger.error(f"No air date available for {log_id}")
                        skip_remaining = True
                else:
                    # Episode doesn't exist in TVMaze
                    if not season_exists:
                        logger.error(f"{show.title} S{season.number} not in TVMaze")
                        break  # Exit episode loop since whole season is missing
                    elif not trakt_time:
                        logger.error(f"No air date available for {log_id}")
                        skip_remaining = True
            
                # Check if the final release time is more than a week away
                if episode.aired_at:
                    # Get current time in the same timezone as episode.aired_at
                    now = datetime.now(episode.aired_at.tzinfo)
                    time_until_release = episode.aired_at - now
                    if time_until_release.days > 7:
                        logger.debug(f"Skipping remaining episodes - {log_id} is {time_until_release.days} days away")
                        skip_remaining = True
