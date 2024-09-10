from RTN import parse

from program.media.item import MediaItem
from program.media.state import States
from program.settings.manager import settings_manager


DEFAULT_VIDEO_EXTENSIONS = ["mp4", "mkv", "avi"]
ALLOWED_VIDEO_EXTENSIONS = ["mp4", "mkv", "avi", "mov", "wmv", "flv", "m4v", "webm", "mpg", "mpeg", "m2ts", "ts"]

VIDEO_EXTENSIONS = settings_manager.settings.downloaders.video_extensions or DEFAULT_VIDEO_EXTENSIONS
VIDEO_EXTENSIONS = [ext for ext in VIDEO_EXTENSIONS if ext in ALLOWED_VIDEO_EXTENSIONS]

if not VIDEO_EXTENSIONS:
    VIDEO_EXTENSIONS = DEFAULT_VIDEO_EXTENSIONS


class FileFinder:
    """
    A class that helps you find files.

    Attributes:
        filename_attr (str): The name of the file attribute.
    """

    def __init__(self, name, size):
        self.filename_attr = name
        self.filesize_attr = size

    def get_cached_container(self, needed_media: dict[int, list[int]], break_pointer: list[bool] = [False], container: dict = {}) -> dict:
        if not needed_media or len(container) >= len([episode for season in needed_media for episode in needed_media[season]]):
            matched_files = self.cache_matches(container, needed_media, break_pointer)
            if matched_files:
                return {"all_files": container, "matched_files": matched_files}
        return {}

    def filename_matches_show(self, filename):
        try:
            parsed_data = parse(filename)
            return parsed_data.seasons[0], parsed_data.episodes
        except Exception:
            return None, None

    def filename_matches_movie(self, filename):
        try:
            parsed_data = parse(filename)
            return parsed_data.type == "movie"
        except Exception:
            return None

    def cache_matches(self, cached_files: dict, needed_media: dict[int, list[int]], break_pointer: list[bool] = [False]):
        if needed_media:
            # Convert needed_media to a set of (season, episode) tuples
            needed_episodes = {(season, episode) for season in needed_media for episode in needed_media[season]}
            matches_dict = {}

            for file in cached_files.values():
                if break_pointer[1] and break_pointer[0]:
                    break
                matched_season, matched_episodes = self.filename_matches_show(file[self.filename_attr])
                if matched_season and matched_episodes:
                    for episode in matched_episodes:
                        if (matched_season, episode) in needed_episodes:
                            if matched_season not in matches_dict:
                                matches_dict[matched_season] = {}
                            matches_dict[matched_season][episode] = file
                            needed_episodes.remove((matched_season, episode))

            if not needed_episodes:
                return matches_dict
        else:
            biggest_file = max(cached_files.values(), key=lambda x: x[self.filesize_attr])
            if biggest_file and self.filename_matches_movie(biggest_file[self.filename_attr]):
                return {1: {1: biggest_file}}

def get_needed_media(item: MediaItem) -> dict:
    acceptable_states = [States.Indexed, States.Scraped, States.Unknown, States.Failed, States.PartiallyCompleted]
    if item.type == "movie":
        needed_media = None
    elif item.type == "show":
        needed_media = {season.number: [episode.number for episode in season.episodes if episode.state in acceptable_states] for season in item.seasons if season.state in acceptable_states}
    elif item.type == "season":
        needed_media = {item.number: [episode.number for episode in item.episodes if episode.state in acceptable_states]}
    elif item.type == "episode":
        needed_media = {item.parent.number: [item.number]}
    return needed_media