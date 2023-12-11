"""MediaItem module"""

from enum import IntEnum
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import datetime
import re
import threading
import dill


class MediaItemState(IntEnum):
    """MediaItem states"""

    ERROR = -1
    UNKNOWN = 1
    LIBRARY = 2
    LIBRARY_ONGOING = 3
    LIBRARY_METADATA = 4
    CONTENT = 5
    SCRAPED = 6
    SCRAPED_NOT_FOUND = 7
    PARTIALLY_SCRAPED = 8
    DOWNLOADING = 9
    PARTIALLY_DOWNLOADING = 10

class MediaItem:
    """MediaItem class"""

    def __init__(self, item):
        self._lock = threading.Lock()
        # self._state = item.get("state", MediaItemState.UNKNOWN)
        self.scraped_at = 0
        self.active_stream = item.get("active_stream", None)
        self.streams = {}

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
        self.art_url = item.get("art_url", None)

    def to_dict(self):
        return {
            "title": self.title,
            "imdb_id": self.imdb_id,
            "imdb_link": self.imdb_link if hasattr(self, 'imdb_link') else None,
            "aired_at": self.aired_at,
            "genres": self.genres,
            "key": self.key,
            "guid": self.guid,
            "art_url": self.art_url,
            "is_cached": self.is_cached(),
            "is_checked_for_availability": self.is_checked_for_availability()
        }

    def is_cached(self):
        if self.streams:
            return any(stream.get("cached", None) for stream in self.streams.values())
        return False

    def is_checked_for_availability(self):
        if self.streams:
            return all(
                stream.get("cached", None) is not None
                for stream in self.streams.values()
            )
        return False

    def is_not_cached(self):
        return not self.is_cached()

    def __iter__(self):
        with self._lock:
            for attr, _ in vars(self).items():
                yield attr

    def __eq__(self, other):
        with self._lock:
            value = False
            if self.imdb_id and other.imdb_id:
                value = self.imdb_id == other.imdb_id
            return value

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
        self.file_name = item.get("file_name", None)
        self.scrape_pattern = None

    @property
    def state(self):
        if self.key:
            return MediaItemState.LIBRARY
        if any(stream.get("cached", None) for stream in self.streams.values()):
            return MediaItemState.DOWNLOADING
        if len(self.streams) > 0:
            return MediaItemState.SCRAPED
        return MediaItemState.CONTENT

    def __eq__(self, other):
        return isinstance(self, type(other)) and (
            super().__eq__(other)
            or self.file_name is not None
            and self.file_name == other.file_name
        )

    def __repr__(self):
        return f"Movie:{self.title}:{self.state}"


class Show(MediaItem):
    """Show class"""

    def __init__(self, item):
        super().__init__(item)
        self.locations = item.get("locations", [])
        self.seasons = item.get("seasons", [])
        self.type = "show"

    def __eq__(self, other):
        return isinstance(self, type(other)) and (
            any(location in other.locations for location in self.locations)
            or super().__eq__(other)
        )

    def _len_library_seasons(self):
        return len(
            [
                season
                for season in self.seasons
                if season.state
                in [MediaItemState.LIBRARY, MediaItemState.LIBRARY_ONGOING]
            ]
        )

    @property
    def state(self):
        if any(
            season.state == MediaItemState.LIBRARY_ONGOING for season in self.seasons
        ):
            return MediaItemState.LIBRARY_ONGOING
        if all(season.state == MediaItemState.LIBRARY for season in self.seasons):
            return MediaItemState.LIBRARY
        if all(season.state == MediaItemState.DOWNLOADING for season in self.seasons):
            return MediaItemState.DOWNLOADING
        if any(
            season.state
            in [MediaItemState.DOWNLOADING, MediaItemState.PARTIALLY_DOWNLOADING]
            for season in self.seasons
        ):
            return MediaItemState.PARTIALLY_DOWNLOADING
        return MediaItemState.CONTENT

    def __repr__(self):
        return f"Show:{self.title}:{self.state}"

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
        if len(self.episodes) == len(
            [
                episode
                for episode in self.episodes
                if episode.state == MediaItemState.LIBRARY
            ]
        ):
            return MediaItemState.LIBRARY
        if any(episode.state == MediaItemState.LIBRARY for episode in self.episodes):
            return MediaItemState.LIBRARY_ONGOING
        if self.is_cached():
            return MediaItemState.DOWNLOADING
        if (
            not self.is_checked_for_availability()
            and self.streams
            and len(self.streams) > 0
        ):
            return MediaItemState.SCRAPED
        if self.is_checked_for_availability() and not self.is_cached():
            return MediaItemState.SCRAPED_NOT_FOUND
        return MediaItemState.CONTENT

    def __eq__(self, other):
        return self.number == other.number

    def __repr__(self):
        return f"Season:{self.number}:{self.state}"

    def add_episode(self, episode):
        """Add episode to season"""
        with self._lock:
            self.episodes.append(episode)
            episode.parent = self

    def get_real_episode_count(self):
        file_names = [episode.file_name for episode in self.episodes]

        episode_numbers = []
        for file_name in file_names:
            episode_numbers.extend(
                re.findall(r"E(\d{1,2}(?:-\d{1,2})?)", file_name, re.IGNORECASE)
            )
        return count_episodes(episode_numbers)


class Episode(MediaItem):
    """Episode class"""

    def __init__(self, item):
        super().__init__(item)
        self.type = "episode"
        self.parent = None
        self.number = item.get("number", None)
        self.file_name = item.get("file_name", None)

    @property
    def state(self):
        if self.key:
            return MediaItemState.LIBRARY
        if self.is_cached():
            return MediaItemState.DOWNLOADING
        if len(self.streams) > 0:
            return MediaItemState.SCRAPED
        return MediaItemState.CONTENT

    def __eq__(self, other):
        return self.number == other.number

    def __repr__(self):
        return f"Episode:{self.number}:{self.state}"

    def get_multi_episode_numbers(self):
        file_episodes = []
        if self.file_name:

            def is_episode_segment(segment):
                # Remove season prefix
                no_season_segment = re.sub(r"S\d{1,2}", "", segment, flags=re.I)

                # Extract potential episode patterns without the season prefix
                extracted_episodes = re.findall(
                    r"E\d{1,2}", no_season_segment, flags=re.I
                )
                if extracted_episodes:
                    # Check validity of segment
                    constructed_string = "".join(extracted_episodes)
                    return (
                        no_season_segment.lower() == constructed_string.lower()
                        or no_season_segment.lower()
                        == f"{extracted_episodes[0]}-{extracted_episodes[-1]}".lower()
                    )

            def extract_numeric_episodes(segment):
                if is_episode_segment(segment):
                    # Extract numeric part of episode patterns
                    return re.findall(r"E(\d{1,2})", segment, flags=re.I)
                return []

            segments = re.split(r"[ .-]", self.file_name)
            file_episodes = [
                str(int(episode))
                for segment in segments
                for episode in extract_numeric_episodes(segment)
            ]

        return file_episodes


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
