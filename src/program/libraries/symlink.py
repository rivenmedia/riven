import os
import re
from pathlib import Path

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.subtitle import Subtitle
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
        """Validate the symlink library settings."""
        library_path = Path(self.settings.library_path).resolve()
        if library_path == Path.cwd().resolve():
            logger.error("Library path not set or set to the current directory in SymlinkLibrary settings.")
            return False

        required_dirs: list[str] = ["shows", "movies"]
        if self.settings.separate_anime_dirs:
            required_dirs.extend(["anime_shows", "anime_movies"])
        missing_dirs: list[str] = [d for d in required_dirs if not (library_path / d).exists()]

        if missing_dirs:
            available_dirs: str = ", ".join(os.listdir(library_path))
            logger.error(f"Missing required directories in the library path: {', '.join(missing_dirs)}.")
            logger.debug(f"Library directory contains: {available_dirs}")
            return False
        return True

    def run(self):
        """
        Create a library from the symlink paths. Return stub items that should
        be fed into an Indexer to have the rest of the metadata filled in.
        """
        for directory, item_type, is_anime in [("shows", "show", False), ("anime_shows", "anime show", True)]:
            if not self.settings.separate_anime_dirs and is_anime:
                continue
            yield from process_shows(self.settings.library_path / directory, item_type, is_anime)

        for directory, item_type, is_anime in [("movies", "movie", False), ("anime_movies", "anime movie", True)]:
            if not self.settings.separate_anime_dirs and is_anime:
                continue
            yield from process_items(self.settings.library_path / directory, Movie, item_type, is_anime)


def process_items(directory: Path, item_class, item_type: str, is_anime: bool = False):
    """Process items in the given directory and yield MediaItem instances."""
    items = [
        (Path(root), file)
        for root, _, files in os.walk(directory)
        for file in files
        if not file.endswith('.srt')
    ]
    for path, filename in items:
        if filename.endswith(".srt"):
            continue
        imdb_id = re.search(r"(tt\d+)", filename)
        title = re.search(r"(.+)?( \()", filename)
        if not imdb_id or not title:
            logger.error(f"Can't extract {item_type} imdb_id or title at path {path / filename}")
            continue

        item = item_class({"imdb_id": imdb_id.group(), "title": title.group(1)})
        resolve_symlink_and_set_attrs(item, path / filename)
        find_subtitles(item, path / filename)

        if settings_manager.settings.force_refresh:
            item.set("symlinked", True)
            item.set("update_folder", str(path))
        else:
            item.set("symlinked", True)
            item.set("update_folder", "updated")
        if is_anime:
            item.is_anime = True
        yield item

def resolve_symlink_and_set_attrs(item, path: Path) -> Path:
    # Resolve the symlink path
    resolved_path = (path).resolve()
    item.file = str(resolved_path.stem)
    item.folder = str(resolved_path.parent.stem)
    item.symlink_path = str(path)

def find_subtitles(item, path: Path):
    # Scan for subtitle files
    for file in os.listdir(path.parent):
        if file.startswith(Path(item.symlink_path).stem) and file.endswith(".srt"):
            lang_code = file.split(".")[1]
            item.subtitles.append(Subtitle({lang_code: (path.parent / file).__str__()}))
            logger.debug(f"Found subtitle file {file}.")

def process_shows(directory: Path, item_type: str, is_anime: bool = False) -> Show:
    """Process shows in the given directory and yield Show instances."""
    for show in os.listdir(directory):
        imdb_id = re.search(r"(tt\d+)", show)
        title = re.search(r"(.+)?( \()", show)
        if not imdb_id or not title:
            logger.log("NOT_FOUND", f"Can't extract {item_type} imdb_id or title at path {directory / show}")
            continue
        show_item = Show({"imdb_id": imdb_id.group(), "title": title.group(1)})
        if is_anime:
            show_item.is_anime = True
        seasons = {}
        for season in os.listdir(directory / show):
            if not (season_number := re.search(r"(\d+)", season)):
                logger.log("NOT_FOUND", f"Can't extract season number at path {directory / show / season}")
                continue
            season_item = Season({"number": int(season_number.group())})
            episodes = {}
            for episode in os.listdir(directory / show / season):
                if not (episode_number := re.search(r"s\d+e(\d+)", episode)):
                    logger.log("NOT_FOUND", f"Can't extract episode number at path {directory / show / season / episode}")
                    # Delete the episode since it can't be indexed
                    os.remove(directory / show / season / episode)
                    continue

                episode_item = Episode({"number": int(episode_number.group(1))})
                resolve_symlink_and_set_attrs(episode_item, Path(directory) / show / season / episode)
                find_subtitles(episode_item, Path(directory) / show / season / episode)
                if settings_manager.settings.force_refresh:
                    episode_item.set("symlinked", True)
                    episode_item.set("update_folder", str(Path(directory) / show / season / episode))
                else:
                    episode_item.set("symlinked", True)
                    episode_item.set("update_folder", "updated")
                if is_anime:
                    episode_item.is_anime = True
                episodes[int(episode_number.group(1))] = episode_item
            if len(episodes) > 0:
                for i in range(1, max(episodes.keys())+1):
                    season_item.add_episode(episodes.get(i, Episode({"number": i})))
                seasons[int(season_number.group())] = season_item
        if len(seasons) > 0:
            for i in range(1, max(seasons.keys())+1):
                show_item.add_season(seasons.get(i, Season({"number": i})))
        yield show_item