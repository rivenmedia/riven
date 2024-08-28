import contextlib
from posixpath import splitext
from RTN import parse
from RTN.exceptions import GarbageTorrent

from program.media.item import MediaItem
from program.media.state import States

WANTED_FORMATS = {".mkv", ".mp4", ".avi"}

class FileFinder:
    """
    A class that helps you find files.

    Attributes:
        filename_attr (str): The name of the file attribute.
        filesize_attr (str): The size of the file attribute.
        min_filesize (int): The minimum file size.
        max_filesize (int): The maximum file size.
    """

    def __init__(self, name, size, min, max):
        self.filename_attr = name
        self.filesize_attr = size
        self.min_filesize = min
        self.max_filesize = max
        
    def find_required_files(self, item, container):
        """
        Find the required files based on the given item and container.

        Args:
            item (Item): The item object representing the movie, show, season, or episode.
            container (list): The list of files to search through.

        Returns:
            list: A list of files that match the criteria based on the item type.
                Returns an empty list if no files match the criteria.

        """
        files = [
            file
            for file in container
            if file and self.min_filesize < file[self.filesize_attr] < self.max_filesize
            and file[self.filesize_attr] > 10000
            and splitext(file[self.filename_attr].lower())[1] in WANTED_FORMATS
        ]
        return_files = []

        if not files:
            return []

        if item.type == "movie":
            for file in files:
                with contextlib.suppress(GarbageTorrent, TypeError):
                    parsed_file = parse(file[self.filename_attr])
                    if parsed_file.type == "movie":
                        return_files.append(file)
        if item.type == "show":
            needed_episodes = {}
            acceptable_states = [States.Indexed, States.Scraped, States.Unknown, States.Failed, States.PartiallyCompleted]

            for season in item.seasons:
                if season.state in acceptable_states and season.is_released_nolog:
                    needed_episode_numbers = {episode.number for episode in season.episodes if episode.state in acceptable_states and episode.is_released_nolog}
                    if needed_episode_numbers:
                        needed_episodes[season.number] = needed_episode_numbers

            if not any(needed_episodes.values()):
                return return_files

            matched_files = {}
            one_season = len(item.seasons) == 1

            for file in files:
                with contextlib.suppress(GarbageTorrent, TypeError):
                    parsed_file = parse(file[self.filename_attr])
                    if not parsed_file or not parsed_file.episodes or 0 in parsed_file.seasons:
                        continue

                    # Check each season and episode to find a match
                    for season_number, episodes in needed_episodes.items():
                        if one_season or season_number in parsed_file.seasons:
                            for episode_number in parsed_file.episodes:
                                if episode_number in episodes:
                                    # Store the matched file for this episode
                                    matched_files.setdefault((season_number, episode_number), []).append(file)
                                    
            # total_needed_episodes = sum(len(episodes) for episodes in needed_episodes.values())
            # matched_episodes = sum(len(files) for files in matched_files.values())
                    
            if set(needed_episodes).issubset(matched_files):
                for key, files in matched_files.items():
                    season_number, episode_number = key
                    for file in files:
                        if not file or "sample" in file[self.filename_attr].lower():
                            continue
                        return_files.append(file)
                                    
        if item.type == "season":
            acceptable_states = [States.Indexed, States.Scraped, States.Unknown, States.Failed, States.PartiallyCompleted]
            needed_episodes = []
            for episode in item.episodes:
                if episode.state in acceptable_states and episode.is_released_nolog:
                    needed_episodes.append(episode.number)

            if not needed_episodes:
                return return_files
            
            matched_files = {}
            one_season = len(item.parent.seasons) == 1
            
            for file in files:
                with contextlib.suppress(GarbageTorrent, TypeError):
                    parsed_file = parse(file[self.filename_attr])
                    if not parsed_file or not parsed_file.episodes or 0 in parsed_file.seasons:
                        continue

                    if one_season or item.number in parsed_file.seasons:
                        for episode_number in parsed_file.episodes:
                            if episode_number in needed_episodes:
                                matched_files.setdefault(episode_number, []).append(file)
                                
            # matched_episodes = sum(len(files) for files in matched_files.values())

            if set(needed_episodes).issubset(matched_files):
                for files in matched_files.values():
                    for file in files:
                        if not file or "sample" in file[self.filename_attr].lower():
                            continue
                        return_files.append(file)

        if item.type == "episode":
            for file in files:
                if not file or not file.get(self.filename_attr):
                    continue
                with contextlib.suppress(GarbageTorrent, TypeError):
                    parsed_file = parse(file[self.filename_attr])
                    if (
                        item.number in parsed_file.episodes
                        and item.parent.number in parsed_file.seasons
                    ):
                        return_files.append(file)
                    elif len(item.parent.parent.seasons) == 1 and item.number in parsed_file.episodes:
                        return_files.append(file)

        return return_files

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