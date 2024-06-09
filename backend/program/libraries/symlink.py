import os
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Tuple

import regex
from program.indexers.trakt import TraktIndexer, create_item_from_imdb_id
from program.media.container import MediaItemContainer
from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.settings.manager import settings_manager
from utils.logger import logger


class SymlinkLibrary:
    def __init__(self, trakt_indexer: TraktIndexer, media_items: MediaItemContainer):
        self.key = "symlinklibrary"
        self.settings = settings_manager.settings.symlink
        self.indexer = trakt_indexer
        self.media_items = media_items
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
        """Generate media items from the symlink paths."""
        for movie_item in self.process_movies():
            yield movie_item

        for show_item in self.process_shows():
            yield show_item

    def _process_item(self, new_item, existing_item=None):
        """Process the item by making necessary API calls and updating the media items container."""
        if existing_item:
            existing_item.copy_other_media_attr(new_item)
            if new_item.symlinked:
                existing_item.set("update_folder", "updated")
            else:
                existing_item.state = self._determine_state(existing_item)
            self._fetch_and_update_metadata(existing_item)
            self.media_items.upsert(existing_item)
        else:
            if new_item.symlinked:
                new_item.set("update_folder", "updated")
            else:
                new_item.state = self._determine_state(new_item)
            self._fetch_and_update_metadata(new_item)
            self.media_items.upsert(new_item)

    def process_movies(self) -> Generator[Movie, None, None]:
        """Process movie symlinks and yield Movie items."""
        movies = self.get_files_in_directory(self.settings.library_path / "movies")
        for path, filename in movies:
            imdb_id = self.extract_imdb_id(filename)
            if not imdb_id:
                logger.error(f"Can't extract movie imdb_id or title at path {path / filename}")
                continue
            movie_item = Movie({"imdb_id": imdb_id})
            movie_item.set("symlinked", True)
            movie_item.set("update_folder", "updated")
            movie_item.set("requested_by", "symlink")
            movie_item.set("file", filename)
            movie_item.set("folder", path)
            yield movie_item

    def process_shows(self) -> Generator[Show, None, None]:
        """Process show symlinks and yield Show items."""
        shows_dir = self.settings.library_path / "shows"
        for show in os.listdir(shows_dir):
            imdb_id = self.extract_imdb_id(show)
            if not imdb_id:
                logger.error(f"Can't extract show imdb_id at path {shows_dir / show}")
                continue
            show_item = Show({"imdb_id": imdb_id})
            self.media_items.upsert(show_item)  # Ensure the show is added to the container
            for season_item in self.process_seasons(shows_dir / show, show_item):
                show_item.add_season(season_item)
                self.media_items.upsert(season_item)  # Ensure the season is added to the container
            yield show_item

    def process_seasons(self, show_path: Path, show_item: Show) -> Generator[Season, None, None]:
        """Process season symlinks and yield Season items."""
        for season in os.listdir(show_path):
            season_number = self.extract_season_number(season)
            if not season_number:
                logger.error(f"Can't extract season number at path {show_path / season}")
                continue
            season_item = Season({"number": season_number, "parent_id": show_item.item_id})
            for episode_item in self.process_episodes(show_path / season, season_item):
                season_item.add_episode(episode_item)
            yield season_item

    def process_episodes(self, season_path: Path, season_item: Season) -> Generator[Episode, None, None]:
        """Process episode symlinks and yield Episode items."""
        for episode in os.listdir(season_path):
            episode_number = self.extract_episode_number(episode)
            episode_title = self.extract_title(episode)
            if not episode_number or not episode_title:
                logger.error(f"Deleting symlink, unable to extract episode number: {season_path / episode}")
                # os.remove(season_path / episode)
                continue
            episode_item = Episode({
                "number": episode_number,
                "parent_id": season_item.item_id,
                "title": episode_title,
            })
            episode_item.set("symlinked", True)
            episode_item.set("update_folder", "updated")
            yield episode_item

    def _fetch_and_update_metadata(self, item):
        """Fetch and update metadata for an item if it is missing."""
        if not item.title or not item.aired_at:
            metadata = self.indexer.create_item_from_imdb_id(item.imdb_id)
            if metadata:
                item.copy_other_media_attr(metadata)
                logger.debug(f"Fetched and updated metadata for {item.log_string}")

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
