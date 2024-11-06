"""Trakt updater module"""

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
                for episode in season.episodes:
                    episode_item = self.api.map_item_from_data(episode, "episode", show.genres)
                    if episode_item:
                        season_item.add_episode(episode_item)
                show.add_season(season_item)





