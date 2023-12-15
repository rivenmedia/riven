"""MediaItem module"""

from enum import IntEnum
from typing import List, Optional
from datetime import datetime
import datetime
import threading
import dill
import PTN


class MediaItemState(IntEnum):
    """MediaItem states"""

    UNKNOWN = 0
    CONTENT = 1
    SCRAPE = 2
    DOWNLOAD = 3
    SYMLINK = 4
    LIBRARY = 5
    LIBRARY_PARTIAL = 6

class MediaItem:
    """MediaItem class"""

    def __init__(self, item):
        self._lock = threading.Lock()
        self.scraped_at = 0
        self.active_stream = item.get("active_stream", None)
        self.streams = {}
        self.symlinked = False

        # Media related
        self.title = item.get("title", None)
        self.imdb_id = item.get("imdb_id", None)
        if self.imdb_id:
            self.imdb_link = f"https://www.imdb.com/title/{self.imdb_id}/"
        self.aired_at = item.get("aired_at", None)
        self.genres = item.get("genres", [])

        # Plex related
        self.key = item.get("key", None)
        self.guid = item.get("guid", None)

    @property
    def state(self):
        if self.key:
            return MediaItemState.LIBRARY
        if self.symlinked:
            return MediaItemState.SYMLINK
        if self.is_cached():
            return MediaItemState.DOWNLOAD
        if len(self.streams) > 0:
            return MediaItemState.SCRAPE
        if self.title:
            return MediaItemState.CONTENT
        return MediaItemState.UNKNOWN

    def is_cached(self):
        if self.streams:
            return any(stream.get("cached", None) for stream in self.streams.values())
        return False

    def is_scraped(self):
        return len(self.streams) > 0

    def is_checked_for_availability(self):
        if self.streams:
            return all(
                stream.get("cached", None) is not None
                for stream in self.streams.values()
            )
        return False

    def to_dict(self):
        return {
            "title": self.title,
            "imdb_id": self.imdb_id,
            "state": self.state.name,
            "imdb_link": self.imdb_link if hasattr(self, 'imdb_link') else None,
            "aired_at": self.aired_at,
            "genres": self.genres,
            "guid": self.guid,
        }

    def is_not_cached(self):
        return not self.is_cached()

    def __iter__(self):
        with self._lock:
            for attr, _ in vars(self).items():
                yield attr

    def __eq__(self, other):
        with self._lock:
            if isinstance(other, type(self)):
                return self.imdb_id == other.imdb_id
            return False

    def get(self, key, default=None):
        """Get item attribute"""
        with self._lock:
            return getattr(self, key, default)

    def set(self, key, value):
        """Set item attribute"""
        with self._lock:
            _set_nested_attr(self, key, value)


class Movie(MediaItem):
    """Movie class"""

    def __init__(self, item):
        super().__init__(item)
        self.type = "movie"
        self.file = item.get("file", None)

    def __repr__(self):
        return f"Movie:{self.title}:{self.state.name}"


class Show(MediaItem):
    """Show class"""

    def __init__(self, item):
        super().__init__(item)
        self.locations = item.get("locations", [])
        self.seasons = item.get("seasons", [])
        self.type = "show"

    @property
    def state(self):
        if all(season.state is MediaItemState.LIBRARY for season in self.seasons):
            return MediaItemState.LIBRARY
        if any(season.state in [MediaItemState.LIBRARY, MediaItemState.LIBRARY_PARTIAL] for season in self.seasons):
            return MediaItemState.LIBRARY_PARTIAL
        if any(season.state == MediaItemState.SYMLINK for season in self.seasons):
            return MediaItemState.SYMLINK
        if any(season.state == MediaItemState.DOWNLOAD for season in self.seasons):
            return MediaItemState.DOWNLOAD
        if any(season.state == MediaItemState.SCRAPE for season in self.seasons):
            return MediaItemState.SCRAPE
        if any(season.state == MediaItemState.CONTENT for season in self.seasons):
            return MediaItemState.CONTENT
        return MediaItemState.UNKNOWN

    def __repr__(self):
        return f"Show:{self.title}:{self.state.name}"

    def add_season(self, season):
        """Add season to show"""
        with self._lock:
            self.seasons.append(season)
            season.parent = self


class Season(MediaItem):
    """Season class"""

    def __init__(self, item):
        super().__init__(item)
        self.type = "season"
        self.parent = None
        self.number = item.get("number", None)
        self.episodes = item.get("episodes", [])

    @property
    def state(self):
        if len(self.episodes) > 0:
            if all(episode.state == MediaItemState.LIBRARY for episode in self.episodes):
                return MediaItemState.LIBRARY
            if any(episode.state == MediaItemState.LIBRARY for episode in self.episodes):
                return MediaItemState.LIBRARY_PARTIAL
            if any(episode.state == MediaItemState.SYMLINK for episode in self.episodes):
                return MediaItemState.SYMLINK
            if self.is_cached() or any(episode.state == MediaItemState.DOWNLOAD for episode in self.episodes):
                return MediaItemState.DOWNLOAD
            if self.is_scraped() or any(episode.state == MediaItemState.SCRAPE for episode in self.episodes):
                return MediaItemState.SCRAPE
            if any(episode.state == MediaItemState.CONTENT for episode in self.episodes):
                return MediaItemState.CONTENT
        return MediaItemState.UNKNOWN

    def __eq__(self, other):
        return self.number == other.number

    def __repr__(self):
        return f"Season:{self.number}:{self.state.name}"

    def add_episode(self, episode):
        """Add episode to season"""
        with self._lock:
            self.episodes.append(episode)
            episode.parent = self


class Episode(MediaItem):
    """Episode class"""

    def __init__(self, item):
        super().__init__(item)
        self.type = "episode"
        self.parent = None
        self.number = item.get("number", None)
        self.file = item.get("file", None)

    @property
    def state(self):
        return super().state

    def __eq__(self, other):
        return self.number == other.number

    def __repr__(self):
        return f"Episode:{self.number}:{self.state.name}"

    def get_file_episodes(self):
        parse = PTN.parse(self.file)
        episode_number = parse.get("episode")
        if type(episode_number) == int:
            episode_number = [episode_number]
        if parse.get("excess"):
            excess_episodes = None
            if type(parse["excess"]) == list:
                for excess in parse["excess"]:
                    excess_parse = PTN.parse(excess)
                    if excess_parse.get("episode") is not None:
                        excess_episodes = excess_parse["episode"]
                        break
            if type(parse["excess"]) == str:
                excess_parse = PTN.parse(parse["excess"])
                if excess_parse.get("episode") is not None:
                    excess_episodes = excess_parse["episode"]
            if excess_episodes:
                episode_number = episode_number + excess_episodes
        return episode_number


class MediaItemContainer:
    """MediaItemContainer class"""

    def __init__(self, items: Optional[List[MediaItem]] = None):
        self.items = items if items is not None else []
        self.updated_at = None

    def __iter__(self):
        for item in self.items:
            yield item

    def __iadd__(self, other):
        if not isinstance(other, MediaItem) and other is not None:
            raise TypeError("Cannot append non-MediaItem to MediaItemContainer")
        if other not in self.items:
            self.items.append(other)
            self._set_updated_at()
        return self

    def __len__(self):
        """Get length of container"""
        return len(self.items)

    def append(self, item) -> bool:
        """Append item to container"""
        self.items.append(item)
        self._set_updated_at()

    def get(self, item) -> MediaItem:
        """Get item matching given item from container"""
        for my_item in self.items:
            if my_item == item:
                return my_item
        return None

    def get_item(self, attr, value) -> "MediaItemContainer":
        """Get items that match given items"""
        return next((item for item in self.items if getattr(item, attr) == value), None)

    def extend(self, items) -> "MediaItemContainer":
        """Extend container with items"""
        added_items = MediaItemContainer()
        for media_item in items:
            if media_item not in self.items:
                self.items.append(media_item)
                added_items.append(media_item)
        return added_items

    def _set_updated_at(self):
        self.updated_at = {
            "length": len(self.items),
            "time": datetime.datetime.now().timestamp(),
        }

    def remove(self, item):
        """Remove item from container"""
        if item in self.items:
            self.items.remove(item)
            self._set_updated_at()

    def count(self, state) -> int:
        """Count items with given state in container"""
        return len(self.get_items_with_state(state))

    def get_items_with_state(self, state):
        """Get items that need to be updated"""
        return MediaItemContainer([item for item in self.items if item.state == state])

    def save(self, filename):
        """Save container to file"""
        with open(filename, "wb") as file:
            dill.dump(self.items, file)

    def load(self, filename):
        """Load container from file"""
        try:
            with open(filename, "rb") as file:
                self.items = dill.load(file)
        except FileNotFoundError:
            self.items = []


def _set_nested_attr(obj, key, value):
    if "." in key:
        parts = key.split(".", 1)
        current_key, rest_of_keys = parts[0], parts[1]

        if not hasattr(obj, current_key):
            raise AttributeError(f"Object does not have the attribute '{current_key}'.")

        current_obj = getattr(obj, current_key)
        _set_nested_attr(current_obj, rest_of_keys, value)
    else:
        if isinstance(obj, dict):
            if key in obj:
                obj[key] = value
        else:
            setattr(obj, key, value)


def count_episodes(episode_nums):
    count = 0
    for ep in episode_nums:
        if "-" in ep:  # Range of episodes
            start, end = map(int, ep.split("-"))
            count += end - start + 1
        else:  # Individual episodes
            count += 1
    return count
