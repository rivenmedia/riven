import os
import re
from pathlib import Path

from utils.logger import logger
from program.settings.manager import settings_manager
from program.media.item import (
    MediaItem,
    Movie,
    Show,
    Season,
    Episode,
    ItemId
)

class SymlinkLibrary:
    def __init__(self):
        self.key = "symlinklibrary"
        self.last_fetch_times = {}
        self.settings = settings_manager.settings.symlink
        self.initialized = True

    def run(self) -> MediaItem:
        """Create a library from the symlink paths.  Return stub items that should
        be fed into an Indexer to have the rest of the metadata filled in."""
        movies = [
            (root, files[0]) 
            for root, _, files 
            in os.walk(self.settings.library_path / "movies") 
            if files
        ]
        for path, filename in movies:
            imdb_id = re.search('(tt\d+)', filename).group()
            movie_item = Movie({'imdb_id': imdb_id})
            movie_item.update_folder = "updated"
            yield movie_item
        
        shows_dir = self.settings.library_path / "shows" 
        for show in os.listdir(shows_dir):
            imdb_id = re.search(r'(tt\d+)', show)
            title = re.search(r'(.+)?( \()', show)
            if not imdb_id or not title:
                logger.error(
                    "Can't extract episode imdb_id or title at path %s", 
                    shows_dir / show
                )
                continue
            show_item = Show({'imdb_id': imdb_id.group(), 'title': title.group(1)})
            for season in os.listdir(shows_dir / show):
                if not (season_number := re.search(r'(\d+)', season)):
                    logger.error(
                        "Can't extract episode number at path %s", 
                        shows_dir / show / season
                    )
                    continue
                season_item = Season({'number': int(season_number.group())})
                for episode in os.listdir(shows_dir / show / season):
                    if not (episode_number := re.search(r's\d+e(\d+)', episode)):
                        logger.error(
                            "Can't extract episode number at path %s", 
                            shows_dir / show / season / episode
                        )
                        continue
                    episode_item = Episode({'number': int(episode_number.group(1))})
                    episode_item.symlinked = True
                    episode_item.update_folder = "updated"
                    season_item.add_episode(episode_item)
                show_item.add_season(season_item)
            yield show_item