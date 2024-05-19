import os
from pathlib import Path
from typing import Generator

import regex
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from utils.logger import logger


class SymlinkLibrary:
    def __init__(self):
        self.key = "symlinklibrary"
        self.last_fetch_times = {}
        self.settings = settings_manager.settings.symlink
        self.initialized = self.validate()
        if not self.initialized:
            logger.error("SymlinkLibrary initialization failed due to invalid configuration.")
            return

    def validate(self) -> bool:
        library_path = Path(self.settings.library_path).resolve()
        if library_path == Path.cwd().resolve():
            logger.error("Library path not set or set to the current directory in SymlinkLibrary settings.")
            return False

        required_dirs = ["shows", "movies"]
        missing_dirs = [d for d in required_dirs if not (library_path / d).exists()]

        if missing_dirs:
            available_dirs = ", ".join(os.listdir(library_path))
            logger.error(f"Missing required directories in the library path: {', '.join(missing_dirs)}.")
            logger.debug(f"Library directory contains: {available_dirs}")
            return False
        return True

    def run(self) -> Generator[MediaItem, None, None]:
        """Create a library from the symlink paths. Return stub items that should be fed into an Indexer to have the rest of the metadata filled in."""
        # Process Movies
        movies = [(root, files[0]) for root, _, files in os.walk(self.settings.library_path / "movies") if files]
        for path, filename in movies:
            imdb_id = regex.search(r"(tt\d+)", filename)
            if not imdb_id:
                logger.error("Can't extract movie imdb_id at path %s", path / filename)
                continue
            movie_item = Movie({"imdb_id": imdb_id.group()})
            movie_item.update_folder = "updated"
            movie_item.symlinked = True
            yield movie_item

        # Process Shows
        shows_dir = self.settings.library_path / "shows"
        for show in os.listdir(shows_dir):
            show_item = self._create_show_item(show)
            if show_item:
                yield show_item

    def _create_show_item(self, show: str) -> Show:
        """Create a Show item from the directory name."""
        shows_dir = self.settings.library_path / "shows"
        show_path = shows_dir / show
        imdb_id = regex.search(r"(tt\d+)", show)
        title = regex.search(r"(.+?)( \()", show)
        if not imdb_id or not title:
            logger.error("Can't extract show imdb_id or title at path %s", show_path)
            return None
        show_item = Show({"imdb_id": imdb_id.group(), "title": title.group(1)})
        self._add_seasons_to_show(show_item, show_path)
        return show_item

    def _add_seasons_to_show(self, show_item: Show, show_path: Path) -> None:
        """Add seasons to the Show item."""
        for season in os.listdir(show_path):
            season_path = show_path / season
            if not (season_number := regex.search(r"(\d+)", season)):
                logger.error("Can't extract season number at path %s", season_path)
                continue
            season_item = Season({"number": int(season_number.group())})
            self._add_episodes_to_season(season_item, season_path)
            show_item.add_season(season_item)

    def _add_episodes_to_season(self, season_item: Season, season_path: Path) -> None:
        """Add episodes to the Season item."""
        for episode in os.listdir(season_path):
            episode_path = season_path / episode
            if not (episode_number := regex.search(r"s\d+e(\d+)", episode, regex.IGNORECASE)):
                logger.error("Can't extract episode number at path %s", episode_path)
                continue
            episode_item = Episode({"number": int(episode_number.group(1))})
            episode_item.symlinked = True
            episode_item.update_folder = "updated"
            season_item.add_episode(episode_item)

def validate_symlink(symlink_path: str, remove: bool = False) -> bool:
    """Validate that the symlink points to a valid target file."""
    if not os.path.islink(symlink_path):
        logger.error("Symlink path %s is not a symlink", symlink_path)
        return False
    target_path = os.readlink(symlink_path)
    if not os.path.exists(target_path):
        logger.error("Symlink target %s does not exist", target_path)
        if remove:
            os.remove(symlink_path)
            logger.debug("Removed invalid symlink %s -> %s", symlink_path, target_path)
        return False
    return True
