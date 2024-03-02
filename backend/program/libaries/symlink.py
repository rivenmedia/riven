import os
import re
from typing import Generator

from utils.logger import logger
from program.settings.manager import settings_manager
from program.media.item import (
    MediaItem,
    Movie,
    Show,
    Season,
    Episode,
)

class SymlinkLibrary:
    def __init__(self):
        self.key = "symlinklibrary"
        self.last_fetch_times = {}
        self.settings = settings_manager.settings.symlink
        self.initialized = True
        self.initialized = self.validate()
        if not self.initialized:
            logger.error("SymlinkLibrary initialization failed due to invalid configuration.")
            return
    
    def validate(self) -> bool:
        status = all(
            os.path.exists(self.settings.library_path / d) 
            for d in ("shows", "movies")
        )
        if not status:
            folders = os.listdir(self.settings.library_path)
            logger.debug("library dir contains %s", ", ".join(folders))
        return status
    
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
            imdb_id = re.search('(tt\d+)', filename)
            if not imdb_id:
                logger.error("Can't extract episode imdb_id at path %s", path / filename)
                continue
            movie_item = Movie({'imdb_id': imdb_id.group()})
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