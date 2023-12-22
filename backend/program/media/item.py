from datetime import datetime
import threading
import program.media.state as states
from utils.utils import parser


class MediaItem:
    """MediaItem class"""

    def __init__(self, item):
        self._lock = threading.Lock()
        self.itemid = item_id.get_next_value()
        self.scraped_at = 0
        self.active_stream = item.get("active_stream", None)
        self.streams = {}
        self.symlinked = False
        self.requested_at = item.get("requested_at", None) or datetime.now()
        self.requested_by = item.get("requested_by", None)

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
        self.updated = None

        self.state.set_context(self)
    
    def perform_action(self):
        self._lock.acquire()
        self.state.perform_action()
        self._lock.release()

    @property
    def state(self):
        _state = self._determine_state()
        _state.set_context(self)
        return _state

    def _determine_state(self):
        if self.key:
            return states.Library()
        if self.symlinked:
            return states.Symlink()
        if self.active_stream or (hasattr(self, "file") and self.file):
            return states.Download()
        if len(self.streams) > 0:
            return states.Scrape()
        if self.title:
            return states.Content()
        return states.Unknown()

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
            "item_id": self.itemid,
            "title": self.title,
            "type": self.type,
            "imdb_id": self.imdb_id,
            "state": self.state.name,
            "imdb_link": self.imdb_link if hasattr(self, "imdb_link") else None,
            "aired_at": self.aired_at,
            "genres": self.genres,
            "guid": self.guid,
            "requested_at": self.requested_at,
            "requested_by": self.requested_by
        }

    def to_extended_dict(self):
        dict = self.to_dict()
        if self.type == "show":
            dict["seasons"] = [season.to_extended_dict() for season in self.seasons]
        if self.type == "season":
            dict["episodes"] = [episode.to_extended_dict() for episode in self.episodes]
        return dict

    def is_not_cached(self):
        return not self.is_cached()

    def __iter__(self):
        for attr, _ in vars(self).items():
            yield attr

    def __eq__(self, other):
        if isinstance(other, type(self)):
            return self.imdb_id == other.imdb_id
        return False

    def get(self, key, default=None):
        """Get item attribute"""
        return getattr(self, key, default)

    def set(self, key, value):
        """Set item attribute"""
        _set_nested_attr(self, key, value)


class Movie(MediaItem):
    """Movie class"""

    def __init__(self, item):
        self.type = "movie"
        self.file = item.get("file", None)
        super().__init__(item)


    def __repr__(self):
        return f"Movie:{self.title}:{self.state.name}"


class Show(MediaItem):
    """Show class"""

    def __init__(self, item):
        self.locations = item.get("locations", [])
        self.seasons = item.get("seasons", [])
        self.type = "show"
        super().__init__(item)


    def _determine_state(self):
        if all(season.state == states.Library for season in self.seasons):
            return states.Library()
        if any(
            season.state == states.LibraryPartial
            for season in self.seasons
        ):
            return states.LibraryPartial()
        if any(season.state == states.Download for season in self.seasons):
            return states.Download()
        if any(season.state == states.Scrape for season in self.seasons):
            return states.Scrape()
        if any(season.state == states.Content for season in self.seasons):
            return states.Content()
        return states.Unknown()

    def __repr__(self):
        return f"Show:{self.title}:{self.state.name}"

    def add_season(self, season):
        """Add season to show"""
        self.seasons.append(season)
        season.parent = self


class Season(MediaItem):
    """Season class"""

    def __init__(self, item):
        self.type = "season"
        self.parent = None
        self.number = item.get("number", None)
        self.episodes = item.get("episodes", [])
        super().__init__(item)


    def _determine_state(self):
        if len(self.episodes) > 0:
            if all(
                episode.state == states.Library for episode in self.episodes
            ):
                return states.Library()
            if any(
                episode.state == states.Library for episode in self.episodes
            ):
                return states.LibraryPartial()
            if all(
                episode.state == states.Symlink for episode in self.episodes
            ):
                return states.Symlink()
            if self.active_stream:
                return states.Download()
            if self.is_scraped():
                return states.Scrape()
            if any(
                episode.state == states.Content for episode in self.episodes
            ):
                return states.Content()
        return states.Unknown()

    def __eq__(self, other):
        return self.number == other.number

    def __repr__(self):
        return f"Season:{self.number}:{self.state.name}"

    def add_episode(self, episode):
        """Add episode to season"""
        self.episodes.append(episode)
        episode.parent = self


class Episode(MediaItem):
    """Episode class"""

    def __init__(self, item):
        self.type = "episode"
        self.parent = None
        self.number = item.get("number", None)
        self.file = item.get("file", None)
        super().__init__(item)


    def __eq__(self, other):
        return self.number == other.number

    def __repr__(self):
        return f"Episode:{self.number}:{self.state.name}"

    def get_file_episodes(self):
        return parser.episodes(self.file)

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
            obj[key] = value
        else:
            setattr(obj, key, value)

class ItemId:
    value = 0

    @classmethod
    def get_next_value(cls):
        cls.value += 1
        return cls.value


item_id = ItemId()