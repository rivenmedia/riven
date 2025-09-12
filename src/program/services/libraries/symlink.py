import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Generator, List, Optional

from loguru import logger
from PTT import parse_title
from sqla_wrapper import Session

from program.db.db import db
from program.media.subtitle import Subtitle
from program.settings.manager import settings_manager

if TYPE_CHECKING:
    from program.media.item import Episode, MediaItem, Movie, Show

imdbid_pattern = re.compile(r"tt\d+")
tvdbid_pattern = re.compile(r"tvdb-(\d+)")
tmdbid_pattern = re.compile(r"tmdb-(\d+)")
season_pattern = re.compile(r"s(\d+)")
episode_pattern = re.compile(r"e(\d+)")

ALLOWED_VIDEO_EXTENSIONS = [
    "mp4",
    "mkv",
    "avi",
    "mov",
    "wmv",
    "flv",
    "m4v",
    "webm",
    "mpg",
    "mpeg",
    "m2ts",
    "ts",
]

MEDIA_DIRS = ["shows", "movies", "anime_shows", "anime_movies"]
POSSIBLE_DIRS = [settings_manager.settings.symlink.library_path / d for d in MEDIA_DIRS]


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

    def run(self) -> list["MediaItem"]:
        """
        Create a library from the symlink paths. Return stub items that should
        be fed into an Indexer to have the rest of the metadata filled in.
        """
        from program.media.item import Movie

        items = []
        for directory, item_type, is_anime in [("shows", "show", False), ("anime_shows", "anime show", True)]:
            if not self.settings.separate_anime_dirs and is_anime:
                continue
            items.extend(process_shows(self.settings.library_path / directory, item_type, is_anime))

        for directory, item_type, is_anime in [("movies", "movie", False), ("anime_movies", "anime movie", True)]:
            if not self.settings.separate_anime_dirs and is_anime:
                continue
            items.extend(process_items(self.settings.library_path / directory, Movie, item_type, is_anime))

        return items

def process_items(directory: Path, item_class, item_type: str, is_anime: bool = False):
    """Process items in the given directory and yield MediaItem instances."""
    from program.media.item import Movie

    items = [
        (Path(root), file)
        for root, _, files in os.walk(directory)
        for file in files
        if os.path.splitext(file)[1][1:] in ALLOWED_VIDEO_EXTENSIONS # Jellyfin/Emby creates extra files
        and Path(root).parent in POSSIBLE_DIRS # MacOS creates extra dirs
    ]
    for path, filename in items:
        if path.parent not in POSSIBLE_DIRS:
            logger.debug(f"Skipping {path.parent} as it's not a valid media directory.")
            continue

        imdb_id = re.search(r"(tt\d+)", filename)
        tvdb_id = re.search(r"tvdb-(\d+)", filename)
        tmdb_id = re.search(r"tmdb-(\d+)", filename)
        title = re.search(r"(.+)?( \()", filename)

        if not imdb_id and not tvdb_id and not tmdb_id or not title:
            logger.error(f"Can't extract {item_type} id or title at path {path / filename}")
            continue

        if item_class == Movie:
            item = item_class({
                "title": title.group(1),
                "imdb_id": imdb_id.group() if imdb_id else None,
                "tmdb_id": tmdb_id.group().replace("tmdb-", "") if tmdb_id else None,
            })
        else:
            item = item_class({
                "title": title.group(1),
                "imdb_id": imdb_id.group() if imdb_id else None,
                "tvdb_id": tvdb_id.group().replace("tvdb-", "") if tvdb_id else None,
            })


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

def process_shows(directory: Path, item_type: str, is_anime: bool = False) -> Generator["Show", None, None]:
    """Process shows in the given directory and yield Show instances."""
    from program.media.item import Episode, Season, Show
    for show in os.listdir(directory):
        imdb_id = re.search(r"(tt\d+)", show)
        tvdb_id = re.search(r"tvdb-(\d+)", show)
        title = re.search(r"(.+)?( \()", show)

        if (not imdb_id and not tvdb_id) or not title:
            logger.log("NOT_FOUND", f"Can't extract {item_type} id or title at path {directory / show}")
            continue

        show_item = Show(
            {
                "title": title.group(1),
                "imdb_id": imdb_id.group() if imdb_id else None,
                "tvdb_id": tvdb_id.group().replace("tvdb-", "") if tvdb_id else None,
            }
        )
        if is_anime:
            show_item.is_anime = True
        seasons = {}
        for season in os.listdir(directory / show):
            if directory not in POSSIBLE_DIRS:
                logger.debug(f"Skipping {directory} as it's not a valid media directory.")
                continue
            # if os.path.splitext(season)[1][1:] not in ALLOWED_VIDEO_EXTENSIONS:
            #     continue
            if not (season_number := re.search(r"(\d+)", season)):
                logger.log("NOT_FOUND", f"Can't extract season number at path {directory / show / season}")
                continue
            season_item = Season({"number": int(season_number.group())})
            episodes = {}
            for episode in os.listdir(directory / show / season):
                if os.path.splitext(episode)[1][1:] not in ALLOWED_VIDEO_EXTENSIONS:
                    continue
                episode_numbers: list[int] = parse_title(episode).get("episodes", [])
                if not episode_numbers:
                    logger.log("NOT_FOUND", f"Can't extract episode number at path {directory / show / season / episode}")
                    # Delete the episode since it can't be indexed
                    os.remove(directory / show / season / episode)
                    continue

                for episode_number in episode_numbers:
                    episode_item = Episode({"number": episode_number})
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
                    episodes[episode_number] = episode_item
            if len(episodes) > 0:
                for i in range(1, max(episodes.keys())+1):
                    season_item.add_episode(episodes.get(i, Episode({"number": i})))
                seasons[int(season_number.group())] = season_item
        if len(seasons) > 0:
            for i in range(1, max(seasons.keys())+1):
                show_item.add_season(seasons.get(i, Season({"number": i})))
        yield show_item


def build_file_map(directory: str) -> dict[str, str]:
    """Build a map of filenames to their full paths in the directory."""
    file_map = {}

    def scan_dir(path):
        with os.scandir(path) as entries:
            for entry in entries:
                if entry.is_file():
                    file_map[entry.name] = entry.path
                elif entry.is_dir():
                    scan_dir(entry.path)

    scan_dir(directory)
    return file_map

def find_broken_symlinks(directory: str) -> list[tuple[str, str]]:
    """Find all broken symlinks in the directory."""
    broken_symlinks = []
    for root, dirs, files in os.walk(directory):
        for name in files + dirs:
            full_path = os.path.join(root, name)
            if os.path.islink(full_path):
                target = os.readlink(full_path)
                if not os.path.exists(os.path.realpath(full_path)):
                    broken_symlinks.append((full_path, target))
    return broken_symlinks

def fix_broken_symlinks(library_path, rclone_path, max_workers=4, specific_directory: Optional[str] = None):
    """Find and fix all broken symlinks in the library path using files from the rclone path."""
    missing_files = 0

    def check_and_fix_symlink(symlink_path, file_map):
        """Check and fix a single symlink."""
        nonlocal missing_files

        if isinstance(symlink_path, tuple):
            symlink_path = symlink_path[0]

        target_path = os.readlink(symlink_path)
        filename = os.path.basename(target_path)
        dirname = os.path.dirname(target_path).split("/")[-1]
        correct_path = file_map.get(filename)
        failed = False

        with db.Session() as session:
            items: Optional[List[Movie | Episode]] = get_items_from_filepath(session, symlink_path)
            if not items:
                # This needs to be improved later.
                # One edge case: The episode has a file already associated with it, but we found another file in rclone for the same episode.
                # We should probably parse the filename and check if the episode already has a file associated with it and clean up if needed.
                logger.log("NOT_FOUND", f"Could not find item in database for path: {symlink_path}")
                return

            if correct_path:
                os.remove(symlink_path)
                os.symlink(correct_path, symlink_path)
                try:
                    for item in items:
                        item = session.merge(item)
                        item.file = filename
                        item.folder = dirname
                        item.symlinked = True
                        item.symlink_path = correct_path
                        item.update_folder = correct_path
                        item.store_state()
                        session.merge(item)
                        session.commit()
                        logger.log("FILES", f"Retargeted broken symlink for {item.log_string} with correct path: {correct_path}")
                except Exception as e:
                    logger.error(f"Failed to fix {item.log_string} with path: {correct_path}: {str(e)}")
                    failed = True
            else:
                os.remove(symlink_path)
                for item in items:
                    item = session.merge(item)
                    item.reset()
                    item.store_state()
                    session.merge(item)
                    session.commit()
                missing_files += 1
                logger.log("FILES", f"Resetting {item.log_string} due to missing file in rclone_path: {filename}")

            if failed:
                logger.warning("Failed to retarget some broken symlinks, recommended action: reset database.")

    def process_directory(directory, file_map):
        """Process a single directory for broken symlinks."""
        if "music" in directory or "pictures" in directory:
            logger.log("FILES", f"Skipping {directory} as it's a music or picture directory.")
            return

        local_broken_symlinks = find_broken_symlinks(directory)
        logger.log("FILES", f"Found {len(local_broken_symlinks)} broken symlinks in {directory}")
        if not local_broken_symlinks:
            return

        with ThreadPoolExecutor(thread_name_prefix="ProcessSymlinkDirectory", max_workers=2) as executor:
            futures = [executor.submit(check_and_fix_symlink, symlink_path, file_map) for symlink_path in local_broken_symlinks]
            for future in as_completed(futures):
                future.result()

    start_time = time.time()
    logger.log("FILES", f"Finding and fixing broken symlinks in {library_path} using files from {rclone_path}")

    file_map = build_file_map(rclone_path)
    if not file_map:
        logger.log("FILES", f"No files found in rclone_path: {rclone_path}. Aborting fix_broken_symlinks.")
        return

    logger.debug(f"Built file map for {rclone_path}")

    if specific_directory:
        library_paths = [specific_directory]
        logger.debug(f"Found specific directory: {library_paths}")
    else:
        valid_dirs = ["shows", "movies", "anime_shows", "anime_movies"]
        library_paths = [os.path.join(library_path, d) for d in valid_dirs if os.path.isdir(os.path.join(library_path, d))]
        logger.debug(f"Found top-level directories: {library_paths}")

    with ThreadPoolExecutor(thread_name_prefix="FixBrokenSymlinks", max_workers=2) as executor:
        futures = [executor.submit(process_directory, directory, file_map) for directory in library_paths]
        if not futures:
            logger.log("FILES", f"No directories found in {library_path}. Aborting fix_broken_symlinks.")
            return
        for future in as_completed(futures):
            future.result()

    end_time = time.time()
    elapsed_time = end_time - start_time
    logger.log("FILES", f"Finished processing and retargeting broken symlinks. Time taken: {elapsed_time:.2f} seconds.")
    logger.log("FILES", f"Reset {missing_files} items to be rescraped due to missing rclone files.")

def get_items_from_filepath(session: Session, filepath: str) -> list["MediaItem"]:
    """Get an item by its filepath."""
    from program.db.db_functions import (
        get_item_by_imdb_and_episode,
        get_item_by_symlink_path,
    )

    tvdb_id_match = tvdbid_pattern.search(filepath)
    tmdb_id_match = tmdbid_pattern.search(filepath)
    season_number_match = season_pattern.search(filepath)
    episode_number_match = episode_pattern.search(filepath)

    if not tvdb_id_match and not tmdb_id_match:
        logger.debug(f"File path missing suitable ID: {filepath}")
        return []

    tvdb_id = tvdb_id_match.group() if tvdb_id_match else None
    tmdb_id = tmdb_id_match.group() if tmdb_id_match else None
    season_number = int(season_number_match.group(1)) if season_number_match else None
    episode_number = int(episode_number_match.group(1)) if episode_number_match else None

    with session:
        items = get_item_by_symlink_path(filepath, session)
        if not items:
            items = get_item_by_imdb_and_episode(tvdb_id, tmdb_id, season_number, episode_number, session)

        return items