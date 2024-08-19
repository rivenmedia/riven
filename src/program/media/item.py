"""MediaItem class"""
from datetime import datetime
import json
from pathlib import Path
from typing import List, Optional, Self
import sqlalchemy
from sqlalchemy import Index

from program.db.db import db
from program.media.state import States
from RTN import parse
from sqlalchemy.orm import Mapped, mapped_column, relationship

from program.media.subtitle import Subtitle
from .stream import  Stream
import utils.websockets.manager as ws_manager

from utils.logger import logger
from ..db.db_functions import blacklist_stream, reset_streams


class MediaItem(db.Model):
    """MediaItem class"""
    __tablename__ = "MediaItem"
    _id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    number: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    type: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    requested_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, default=datetime.now())
    requested_by: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    scraped_times: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)
    active_stream: Mapped[Optional[dict[str]]] = mapped_column(sqlalchemy.JSON, nullable=True)
    streams: Mapped[list[Stream]] = relationship(secondary="StreamRelation", back_populates="parents", lazy="select", cascade="all")
    blacklisted_streams: Mapped[list[Stream]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_parents", lazy="select", cascade="all")
    symlinked: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    symlinked_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    symlinked_times: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)
    symlink_path: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    file: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    alternative_folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    is_anime: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    title: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tvdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tmdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    network: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    aired_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    genres: Mapped[Optional[List[str]]] = mapped_column(sqlalchemy.JSON, nullable=True)
    key: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    guid: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    update_folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    overseerr_id: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    last_state: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, default="Unknown")
    subtitles: Mapped[list[Subtitle]] = relationship(Subtitle, back_populates="parent", lazy="joined", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_identity": "mediaitem",
        "polymorphic_on":"type",
        "with_polymorphic":"*",
    }

    __table_args__ = (
        Index('ix_mediaitem_item_id', 'item_id'),
        Index('ix_mediaitem_type', 'type'),
        Index('ix_mediaitem_requested_by', 'requested_by'),
        Index('ix_mediaitem_title', 'title'),
        Index('ix_mediaitem_imdb_id', 'imdb_id'),
        Index('ix_mediaitem_tvdb_id', 'tvdb_id'),
        Index('ix_mediaitem_tmdb_id', 'tmdb_id'),
        Index('ix_mediaitem_network', 'network'),
        Index('ix_mediaitem_country', 'country'),
        Index('ix_mediaitem_language', 'language'),
        Index('ix_mediaitem_aired_at', 'aired_at'),
        Index('ix_mediaitem_year', 'year'),
        Index('ix_mediaitem_overseerr_id', 'overseerr_id'),
        Index('ix_mediaitem_type_aired_at', 'type', 'aired_at'),  # Composite index
    )
    
    def __init__(self, item: dict | None) -> None:
        if item is None:
            return
        self.requested_at = item.get("requested_at", datetime.now())
        self.requested_by = item.get("requested_by")

        self.indexed_at = None

        self.scraped_at  = None
        self.scraped_times = 0
        self.active_stream = item.get("active_stream", {})
        self.streams: List[Stream] = []
        self.blacklisted_streams: List[Stream] = []

        self.symlinked = False
        self.symlinked_at = None
        self.symlinked_times = 0

        self.file  = None
        self.folder = None
        self.is_anime = item.get("is_anime", False)

        # Media related
        self.title = item.get("title")
        self.imdb_id =  item.get("imdb_id")
        if self.imdb_id:
            self.imdb_link = f"https://www.imdb.com/title/{self.imdb_id}/"
            if not hasattr(self, "item_id"):
                self.item_id = self.imdb_id
        self.tvdb_id = item.get("tvdb_id")
        self.tmdb_id = item.get("tmdb_id")
        self.network = item.get("network")
        self.country = item.get("country")
        self.language = item.get("language")
        self.aired_at = item.get("aired_at")
        self.year = item.get("year")
        self.genres = item.get("genres", [])

        # Plex related
        self.key = item.get("key")
        self.guid = item.get("guid")
        self.update_folder = item.get("update_folder")

        # Overseerr related
        self.overseerr_id = item.get("overseerr_id")

        #Post processing
        self.subtitles = item.get("subtitles", [])

    def store_state(self) -> None:
        if self.last_state != self._determine_state().name:
            ws_manager.send_item_update(json.dumps(self.to_dict()))
        self.last_state = self._determine_state().name
        
    def is_stream_blacklisted(self, stream: Stream):
        """Check if a stream is blacklisted for this item."""
        return stream in self.blacklisted_streams

    def blacklist_stream(self, stream: Stream):
        return blacklist_stream(self, stream)

    @property
    def is_released(self) -> bool:
        """Check if an item has been released."""
        if not self.aired_at:
            return False
        now = datetime.now()
        if self.aired_at > now:
            time_until_release = self.aired_at - now
            days, seconds = time_until_release.days, time_until_release.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds = seconds % 60
            time_message = f"{self.log_string} will be released in {days} days, {hours:02}:{minutes:02}:{seconds:02}"
            logger.log("ITEM", time_message)
            return False
        return True
    
    @property
    def is_released_nolog(self):
        """Check if an item has been released."""
        if not self.aired_at:
            return False
        return True

    @property
    def state(self):
        return self._determine_state()

    def _determine_state(self):
        if self.key or self.update_folder == "updated":
            return States.Completed
        elif self.symlinked:
            return States.Symlinked
        elif self.file and self.folder:
            return States.Downloaded
        elif self.is_scraped():
            return States.Scraped
        elif self.title:
            return States.Indexed
        elif self.imdb_id and self.requested_by:
            return States.Requested
        return States.Unknown

    def copy_other_media_attr(self, other):
        """Copy attributes from another media item."""
        self.title = getattr(other, "title", None)
        self.tvdb_id = getattr(other, "tvdb_id", None)
        self.tmdb_id = getattr(other, "tmdb_id", None)
        self.network = getattr(other, "network", None)
        self.country = getattr(other, "country", None)
        self.language = getattr(other, "language", None)
        self.aired_at = getattr(other, "aired_at", None)
        self.genres = getattr(other, "genres", [])
        self.is_anime = getattr(other, "is_anime", False)
        self.overseerr_id = getattr(other, "overseerr_id", None)

    def is_scraped(self):
        return (len(self.streams) > 0 
                and any(not stream in self.blacklisted_streams for stream in self.streams))

    def to_dict(self):
        """Convert item to dictionary (API response)"""
        return {
            "id": str(self._id),
            "title": self.title,
            "type": self.__class__.__name__,
            "imdb_id": self.imdb_id if hasattr(self, "imdb_id") else None,
            "tvdb_id": self.tvdb_id if hasattr(self, "tvdb_id") else None,
            "tmdb_id": self.tmdb_id if hasattr(self, "tmdb_id") else None,
            "state": self.state.value,
            "imdb_link": self.imdb_link if hasattr(self, "imdb_link") else None,
            "aired_at": str(self.aired_at),
            "genres": self.genres if hasattr(self, "genres") else None,
            "is_anime": self.is_anime if hasattr(self, "is_anime") else False,
            "guid": self.guid,
            "requested_at": str(self.requested_at),
            "requested_by": self.requested_by,
            "scraped_at": str(self.scraped_at),
            "scraped_times": self.scraped_times,
        }

    def to_extended_dict(self, abbreviated_children=False):
        """Convert item to extended dictionary (API response)"""
        dict = self.to_dict()
        match self:
            case Show():
                dict["seasons"] = (
                    [season.to_extended_dict() for season in self.seasons]
                    if not abbreviated_children
                    else self.represent_children
                )
            case Season():
                dict["episodes"] = (
                    [episode.to_extended_dict() for episode in self.episodes]
                    if not abbreviated_children
                    else self.represent_children
                )
        dict["language"] = self.language if hasattr(self, "language") else None
        dict["country"] = self.country if hasattr(self, "country") else None
        dict["network"] = self.network if hasattr(self, "network") else None
        dict["active_stream"] = (
            self.active_stream if hasattr(self, "active_stream") else None
        )
        dict["streams"] = getattr(self, "streams", [])
        dict["blacklisted_streams"] = getattr(self, "blacklisted_streams", [])
        dict["number"] = self.number if hasattr(self, "number") else None
        dict["symlinked"] = self.symlinked if hasattr(self, "symlinked") else None
        dict["symlinked_at"] = (
            self.symlinked_at if hasattr(self, "symlinked_at") else None
        )
        dict["symlinked_times"] = (
            self.symlinked_times if hasattr(self, "symlinked_times") else None
        )
        dict["is_anime"] = self.is_anime if hasattr(self, "is_anime") else None
        dict["update_folder"] = (
            self.update_folder if hasattr(self, "update_folder") else None
        )
        dict["file"] = self.file if hasattr(self, "file") else None
        dict["folder"] = self.folder if hasattr(self, "folder") else None
        dict["symlink_path"] = self.symlink_path if hasattr(self, "symlink_path") else None
        dict["subtitles"] = getattr(self, "subtitles", [])
        return dict

    def __iter__(self):
        for attr, _ in vars(self).items():
            yield attr

    def __eq__(self, other):
        if type(other) == type(self):
            return self._id == other._id
        return False

    def copy(self, other):
        if other is None:
            return None
        self._id = getattr(other, "_id", None)
        self.imdb_id = getattr(other, "imdb_id", None)
        if hasattr(self, "number"):
            self.number = getattr(other, "number", None)
        return self

    def get(self, key, default=None):
        """Get item attribute"""
        return getattr(self, key, default)

    def set(self, key, value):
        """Set item attribute"""
        _set_nested_attr(self, key, value)

    def get_top_title(self) -> str:
        """Get the top title of the item."""
        match self.__class__.__name__:
            case "Season":
                return self.parent.title
            case "Episode":
                return self.parent.parent.title
            case _:
                return self.title

    def __hash__(self):
        return hash(self.item_id)
    
    def reset(self, reset_times: bool = True):
        """Reset item attributes."""
        if self.type == "show":
            for season in self.seasons:
                for episode in season.episodes:
                    episode._reset(reset_times)
                season._reset(reset_times)
        elif self.type == "season":
            for episode in self.episodes:
                episode._reset(reset_times)
        self._reset(reset_times)

    def _reset(self, reset_times: bool = True):
        """Reset item attributes for rescraping."""
        if self.symlink_path:
            if Path(self.symlink_path).exists():
                Path(self.symlink_path).unlink()
            self.set("symlink_path", None)

        try:
            for subtitle in self.subtitles:
                subtitle.remove()
        except Exception as e:
            logger.warning(f"Failed to remove subtitles for {self.log_string}: {str(e)}")

        self.set("file", None)
        self.set("folder", None)
        self.set("alternative_folder", None)

        if self.active_stream:
            active_stream_hash = self.active_stream.get("hash", None)
            reset_streams(self, active_stream_hash)

        self.set("active_stream", {})
        self.set("symlinked", False)
        self.set("symlinked_at", None)
        self.set("update_folder", None)
        self.set("scraped_at", None)

        if reset_times:
            self.set("symlinked_times", 0)
            self.set("scraped_times", 0)

        logger.debug(f"Item {self.log_string} reset for rescraping")

    @property
    def log_string(self):
        return self.title or self.imdb_id

    @property
    def collection(self):
        return self.parent.collection if self.parent else self.item_id


class Movie(MediaItem):
    """Movie class"""
    __tablename__ = "Movie"
    _id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem._id"), primary_key=True)
    __mapper_args__ = {
        "polymorphic_identity": "movie",
        "polymorphic_load": "inline",
    }

    def copy(self, other):
        super().copy(other)
        return self

    def __init__(self, item):
        self.type = "movie"
        self.file = item.get("file", None)
        super().__init__(item)
        self.item_id = self.imdb_id

    def __repr__(self):
        return f"Movie:{self.log_string}:{self.state.name}"

    def __hash__(self):
        return super().__hash__()

class Show(MediaItem):
    """Show class"""
    __tablename__ = "Show"
    _id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem._id"), primary_key=True)
    seasons: Mapped[List["Season"]] = relationship(back_populates="parent", foreign_keys="Season.parent_id", lazy="joined", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_identity": "show",
        "polymorphic_load": "inline",
    }

    def __init__(self, item):
        super().__init__(item)
        self.type = "show"
        self.locations = item.get("locations", [])
        self.seasons: list[Season] = item.get("seasons", [])
        self.item_id = item.get("imdb_id")
        self.propagate_attributes_to_childs()

    def get_season_index_by_id(self, item_id):
        """Find the index of an season by its item_id."""
        for i, season in enumerate(self.seasons):
            if season.item_id == item_id:
                return i
        return None

    def _determine_state(self):
        if all(season.state == States.Completed for season in self.seasons):
            return States.Completed
        if any(
            season.state in (States.Completed, States.PartiallyCompleted)
            for season in self.seasons
        ):
            return States.PartiallyCompleted
        if all(season.state == States.Symlinked for season in self.seasons):
            return States.Symlinked
        if all(season.state == States.Downloaded for season in self.seasons):
            return States.Downloaded
        if self.is_scraped():
            return States.Scraped
        if any(season.state == States.Indexed for season in self.seasons):
            return States.Indexed
        if any(season.state == States.Requested for season in self.seasons):
            return States.Requested
        return States.Unknown

    def store_state(self) -> None:
        for season in self.seasons:
            season.store_state()
        if self.last_state != self._determine_state().name:
            ws_manager.send_item_update(json.dumps(self.to_dict()))
        self.last_state = self._determine_state().name

    def __repr__(self):
        return f"Show:{self.log_string}:{self.state.name}"

    def __hash__(self):
        return super().__hash__()

    def copy(self, other):
        super(Show, self).copy(other)
        self.seasons = []
        for season in other.seasons:
            new_season = Season(item={}).copy(season, False)
            new_season.parent = self
            self.seasons.append(new_season)
        return self

    def fill_in_missing_children(self, other: Self):
        existing_seasons = [s.number for s in self.seasons]
        for s in other.seasons:
            if s.number not in existing_seasons:
                self.add_season(s)
            else:
                existing_season = next(
                    es for es in self.seasons if s.number == es.number
                )
                existing_season.fill_in_missing_children(s)

    def add_season(self, season):
        """Add season to show"""
        if season.number not in [s.number for s in self.seasons]:
            season.is_anime = self.is_anime
            self.seasons.append(season)
            season.parent = self
            #season.item_id.parent_id = self.item_id
            self.seasons = sorted(self.seasons, key=lambda s: s.number)

    def propagate_attributes_to_childs(self):
        """Propagate show attributes to seasons and episodes if they are empty or do not match."""
        # Important attributes that need to be connected.
        attributes = ["genres", "country", "network", "language", "is_anime"]

        def propagate(target, source):
            for attr in attributes:
                source_value = getattr(source, attr, None)
                target_value = getattr(target, attr, None)
                # Check if the attribute source is not falsy (none, false, 0, [])
                # and if the target is not None we set the source to the target
                if (not target_value) and source_value is not None:
                    setattr(target, attr, source_value)

        for season in self.seasons:
            propagate(season, self)
            for episode in season.episodes:
                propagate(episode, self)


class Season(MediaItem):
    """Season class"""
    __tablename__ = "Season"
    _id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem._id"), primary_key=True)
    parent_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Show._id"), use_existing_column=True)
    parent: Mapped["Show"] = relationship(lazy=False, back_populates="seasons", foreign_keys="Season.parent_id")
    episodes: Mapped[List["Episode"]] = relationship(back_populates="parent", foreign_keys="Episode.parent_id", lazy="joined", cascade="all, delete-orphan")
    __mapper_args__ = {
        "polymorphic_identity": "season",
        "polymorphic_load": "inline",
    }
    
    def store_state(self) -> None:
        for episode in self.episodes:
            episode.store_state()
        if self.last_state != self._determine_state().name:
            ws_manager.send_item_update(json.dumps(self.to_dict()))
        self.last_state = self._determine_state().name

    def __init__(self, item):
        self.type = "season"
        self.number = item.get("number", None)
        self.episodes: list[Episode] = item.get("episodes", [])
        self.item_id = self.number
        self.parent = item.get("parent", None)
        super().__init__(item)
        if self.parent and isinstance(self.parent, Show):
            self.is_anime = self.parent.is_anime

    def _determine_state(self):
        if len(self.episodes) > 0:
            if all(episode.state == States.Completed for episode in self.episodes):
                return States.Completed
            if any(episode.state == States.Completed for episode in self.episodes):
                return States.PartiallyCompleted
            if all(episode.state == States.Symlinked for episode in self.episodes):
                return States.Symlinked
            if all(episode.file and episode.folder for episode in self.episodes):
                return States.Downloaded
            if self.is_scraped():
                return States.Scraped
            if any(episode.state == States.Indexed for episode in self.episodes):
                return States.Indexed
            if any(episode.state == States.Requested for episode in self.episodes):
                return States.Requested
        return States.Unknown

    @property
    def is_released(self) -> bool:
        return any(episode.is_released for episode in self.episodes)

    def __repr__(self):
        return f"Season:{self.number}:{self.state.name}"

    def __hash__(self):
        return super().__hash__()

    def copy(self, other, copy_parent=True):
        super(Season, self).copy(other)
        for episode in other.episodes:
            new_episode = Episode(item={}).copy(episode, False)
            new_episode.parent = self
            self.episodes.append(new_episode)
        if copy_parent and other.parent:
            self.parent = Show(item={}).copy(other.parent)
        return self

    def fill_in_missing_children(self, other: Self):
        existing_episodes = [s.number for s in self.episodes]
        for e in other.episodes:
            if e.number not in existing_episodes:
                self.add_episode(e)

    def get_episode_index_by_id(self, item_id):
        """Find the index of an episode by its item_id."""
        for i, episode in enumerate(self.episodes):
            if episode.item_id == item_id:
                return i
        return None

    def represent_children(self):
        return [e.log_string for e in self.episodes]

    def add_episode(self, episode):
        """Add episode to season"""
        if episode.number in [e.number for e in self.episodes]:
            return

        episode.is_anime = self.is_anime
        self.episodes.append(episode)
        episode.parent = self
        self.episodes = sorted(self.episodes, key=lambda e: e.number)

    @property
    def log_string(self):
        return self.parent.log_string + " S" + str(self.number).zfill(2)

    def get_top_title(self) -> str:
        return self.parent.title


class Episode(MediaItem):
    """Episode class"""
    __tablename__ = "Episode"
    _id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem._id"), primary_key=True)
    parent_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Season._id"), use_existing_column=True)
    parent: Mapped["Season"] = relationship(back_populates="episodes", foreign_keys="Episode.parent_id", lazy="joined")

    __mapper_args__ = {
        "polymorphic_identity": "episode",
        "polymorphic_load": "inline",
    }

    def __init__(self, item):
        self.type = "episode"
        self.number = item.get("number", None)
        self.file = item.get("file", None)
        self.item_id = self.number# , parent_id=item.get("parent_id"))
        super().__init__(item)
        if self.parent and isinstance(self.parent, Season):
            self.is_anime = self.parent.parent.is_anime

    def __repr__(self):
        return f"Episode:{self.number}:{self.state.name}"

    def __hash__(self):
        return super().__hash__()

    def copy(self, other, copy_parent=True):
        super(Episode, self).copy(other)
        if copy_parent and other.parent:
            self.parent = Season(item={}).copy(other.parent)
        return self

    def get_file_episodes(self) -> List[int]:
        if not self.file or not isinstance(self.file, str):
            raise ValueError("The file attribute must be a non-empty string.")
        # return list of episodes
        return parse(self.file).episode

    @property
    def log_string(self):
        return f"{self.parent.log_string}E{self.number:02}"

    def get_top_title(self) -> str:
        return self.parent.parent.title

    def get_top_year(self) -> Optional[int]:
        return self.parent.parent.year

    def get_season_year(self) -> Optional[int]:
        return self.parent.year


def _set_nested_attr(obj, key, value):
    if "." in key:
        parts = key.split(".", 1)
        current_key, rest_of_keys = parts[0], parts[1]

        if not hasattr(obj, current_key):
            raise AttributeError(f"Object does not have the attribute '{current_key}'.")

        current_obj = getattr(obj, current_key)
        _set_nested_attr(current_obj, rest_of_keys, value)
    elif isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


def copy_item(item):
    """Copy an item"""
    if isinstance(item, Movie):
        return Movie(item={}).copy(item)
    elif isinstance(item, Show):
        return Show(item={}).copy(item)
    elif isinstance(item, Season):
        return Season(item={}).copy(item)
    elif isinstance(item, Episode):
        return Episode(item={}).copy(item)
    elif isinstance(item, MediaItem):
        return MediaItem(item={}).copy(item)
    else:
        raise ValueError(f"Cannot copy item of type {type(item)}")