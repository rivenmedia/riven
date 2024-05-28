import os
from pathlib import Path
from typing import Generator, List, Tuple

import regex
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from utils.logger import logger


class SymlinkLibrary:
    def __init__(self):
        self.key = "symlinklibrary"
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
        """Create a library from the symlink paths.  Return stub items that should
        be fed into an Indexer to have the rest of the metadata filled in."""
        for movie_item in self.process_movies():
            yield movie_item

        for show_item in self.process_shows():
            yield show_item

    def process_movies(self) -> Generator[Movie, None, None]:
        """Process movie symlinks and yield Movie items."""
        movies = self.get_files_in_directory(self.settings.library_path / "movies")
        for path, filename in movies:
            imdb_id = self.extract_imdb_id(filename)
            if not imdb_id:
                logger.error(f"Can't extract movie imdb_id at path {path / filename}")
                continue
            movie_item = Movie({"imdb_id": imdb_id})
            movie_item.set("symlinked", True)
            movie_item.set("update_folder", "updated")
            yield movie_item

    def process_shows(self) -> Generator[Show, None, None]:
        """Process show symlinks and yield Show items."""
        shows_dir = self.settings.library_path / "shows"
        for show in os.listdir(shows_dir):
            imdb_id = self.extract_imdb_id(show)
            title = self.extract_title(show)
            if not imdb_id or not title:
                logger.error(f"Can't extract episode imdb_id or title at path {shows_dir / show}")
                continue
            show_item = Show({"imdb_id": imdb_id, "title": title})
            for season_item in self.process_seasons(shows_dir / show, show_item):
                show_item.add_season(season_item)
            yield show_item

    def process_seasons(self, show_path: Path, show_item: Show) -> Generator[Season, None, None]:
        """Process season symlinks and yield Season items."""
        for season in os.listdir(show_path):
            season_number = self.extract_season_number(season)
            if not season_number:
                logger.error(f"Can't extract season number at path {show_path / season}")
                continue
            season_item = Season({"number": season_number})
            season_item.set("parent", show_item)
            for episode_item in self.process_episodes(show_path / season, season_item):
                season_item.add_episode(episode_item)
            yield season_item

    def process_episodes(self, season_path: Path, season_item: Season) -> Generator[Episode, None, None]:
        """Process episode symlinks and yield Episode items."""
        for episode in os.listdir(season_path):
            episode_number = self.extract_episode_number(episode)
            if not episode_number:
                logger.debug(f"Deleting episode {season_path / episode} because we can't extract episode number")
                os.remove(season_path / episode)
                continue
            episode_item = Episode({"number": episode_number})
            episode_item.set("parent", season_item)
            episode_item.set("symlinked", True)
            episode_item.set("update_folder", "updated")
            yield episode_item

    @staticmethod
    def get_files_in_directory(directory: Path) -> List[Tuple[Path, str]]:
        """Get all files in a directory."""
        return [
            (root, files[0])
            for root, _, files in os.walk(directory)
            if files
        ]

    @staticmethod
    def extract_imdb_id(text: str) -> str:
        """Extract IMDb ID from text."""
        match = regex.search(r"(tt\d+)", text)
        return match.group() if match else None

    @staticmethod
    def extract_title(text: str) -> str:
        """Extract title from text."""
        match = regex.search(r"(.+?) \(", text)
        return match.group(1) if match else None

    @staticmethod
    def extract_season_number(text: str) -> int:
        """Extract season number from text."""
        match = regex.search(r"(\d+)", text)
        return int(match.group()) if match else None

    @staticmethod
    def extract_episode_number(text: str) -> int:
        """Extract episode number from text."""
        match = regex.search(r"s\d+e(\d+)", text, regex.IGNORECASE)
        return int(match.group(1)) if match else None
