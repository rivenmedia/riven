"""MediaItem class"""
from PTT import parse_title
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Self
import threading
import weakref

import sqlalchemy
from loguru import logger
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from program.db.db import db
from program.managers.websocket_manager import manager as websocket_manager
from program.media.state import States
from program.media.subtitle import Subtitle

from ..db.db_functions import blacklist_stream, reset_streams
from .stream import Stream


class MediaItemPool:
    """Object pool for MediaItem instances to reduce allocation overhead."""

    def __init__(self, max_size: int = 100):
        self._pool = []
        self._max_size = max_size
        self._lock = threading.Lock()
        self._created_count = 0
        self._reused_count = 0

    def get_item(self, item_type: str = "mediaitem") -> 'MediaItem':
        """Get a MediaItem instance from the pool or create a new one."""
        with self._lock:
            if self._pool:
                instance = self._pool.pop()
                self._reused_count += 1
                # Reset the instance for reuse
                instance._reset_for_reuse()
                return instance

        # Create new instance if pool is empty
        self._created_count += 1
        if item_type == "movie":
            return Movie({})
        elif item_type == "show":
            return Show({})
        elif item_type == "season":
            return Season({})
        elif item_type == "episode":
            return Episode({})
        else:
            return MediaItem({})

    def return_item(self, item: 'MediaItem'):
        """Return a MediaItem instance to the pool."""
        if item is None:
            return

        with self._lock:
            if len(self._pool) < self._max_size:
                # Clear sensitive data before returning to pool
                item._prepare_for_pool()
                self._pool.append(item)

    def get_stats(self) -> dict:
        """Get pool statistics."""
        with self._lock:
            return {
                "pool_size": len(self._pool),
                "max_size": self._max_size,
                "created_count": self._created_count,
                "reused_count": self._reused_count,
                "reuse_ratio": self._reused_count / max(1, self._created_count + self._reused_count)
            }


# Global object pool instance
_media_item_pool = MediaItemPool()


class MediaItem(db.Model):
    """MediaItem class"""
    __tablename__ = "MediaItem"
    id: Mapped[str] = mapped_column(sqlalchemy.String, primary_key=True)
    trakt_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tvdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tmdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    number: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    type: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    requested_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, default=datetime.now())
    requested_by: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    requested_id: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    scraped_times: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)
    # Season/episode count tracking for change detection
    last_season_count: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True, default=0)
    last_episode_count: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True, default=0)
    # JSON field to track episode counts per season: {"1": 10, "2": 12, ...}
    season_episode_counts: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, nullable=True, default={})
    # Show status tracking for intelligent re-indexing
    show_status: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)  # "ongoing", "ended", "hiatus", "unknown"
    last_air_date: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    next_air_date: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    status_last_updated: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    active_stream: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, nullable=True)
    streams: Mapped[list[Stream]] = relationship(secondary="StreamRelation", back_populates="parents", lazy="select", cascade="all")
    blacklisted_streams: Mapped[list[Stream]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_parents", lazy="select", cascade="all")
    symlinked: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    symlinked_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    symlinked_times: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)
    symlink_path: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    file: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    alternative_folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    aliases: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, default={})
    is_anime: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
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
    last_state: Mapped[Optional[States]] = mapped_column(sqlalchemy.Enum(States), default=States.Unknown)
    subtitles: Mapped[list[Subtitle]] = relationship(Subtitle, back_populates="parent", lazy="selectin", cascade="all, delete-orphan")
    failed_attempts: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)

    __mapper_args__ = {
        "polymorphic_identity": "mediaitem",
        "polymorphic_on":"type",
        "with_polymorphic":"*",
    }

    __table_args__ = (
        Index("ix_mediaitem_type", "type"),
        Index("ix_mediaitem_requested_by", "requested_by"),
        Index("ix_mediaitem_title", "title"),
        Index("ix_mediaitem_imdb_id", "imdb_id"),
        Index("ix_mediaitem_tvdb_id", "tvdb_id"),
        Index("ix_mediaitem_tmdb_id", "tmdb_id"),
        Index("ix_mediaitem_network", "network"),
        Index("ix_mediaitem_country", "country"),
        Index("ix_mediaitem_language", "language"),
        Index("ix_mediaitem_aired_at", "aired_at"),
        Index("ix_mediaitem_year", "year"),
        Index("ix_mediaitem_overseerr_id", "overseerr_id"),
        Index("ix_mediaitem_type_aired_at", "type", "aired_at"),  # Composite index
    )

    def __init__(self, item: dict | None) -> None:
        if item is None:
            return

        # Optimized initialization using batch attribute setting
        self._initialize_from_dict(item)

    def _initialize_from_dict(self, item: dict):
        """Optimized initialization from dictionary."""
        # Core identification
        self.id = self.__generate_composite_key(item)

        # Batch set attributes using dict comprehension for better performance
        current_time = datetime.now()

        # Request tracking
        self.requested_at = item.get("requested_at", current_time)
        self.requested_by = item.get("requested_by")
        self.requested_id = item.get("requested_id")

        # Processing state (initialize with defaults)
        self.indexed_at = None
        self.scraped_at = None
        self.scraped_times = 0
        self.last_season_count = 0
        self.last_episode_count = 0
        self.season_episode_counts = {}

        # Stream management
        self.active_stream = item.get("active_stream", {})
        self.streams = []
        self.blacklisted_streams = []

        # Symlink state
        self.symlinked = False
        self.symlinked_at = None
        self.symlinked_times = 0

        # File management
        self.file = None
        self.folder = None
        self.is_anime = item.get("is_anime", False)

        # Media metadata (batch assignment)
        media_attrs = {
            'title': None, 'trakt_id': None, 'imdb_id': None, 'tvdb_id': None,
            'tmdb_id': None, 'network': None, 'country': None, 'language': None,
            'aired_at': None, 'year': None
        }

        for attr in media_attrs:
            setattr(self, attr, item.get(attr))

        # Handle imdb_link separately (conditional)
        if self.imdb_id:
            self.imdb_link = f"https://www.imdb.com/title/{self.imdb_id}/"

        # Collections with defaults
        self.genres = item.get("genres", [])
        self.aliases = item.get("aliases", {})

        # Service-specific attributes
        self.key = item.get("key")
        self.guid = item.get("guid")
        self.update_folder = item.get("update_folder")
        self.overseerr_id = item.get("overseerr_id")
        self.subtitles = item.get("subtitles", [])

    def _reset_for_reuse(self):
        """Reset instance for object pool reuse."""
        # Clear all mutable attributes
        self.streams.clear()
        self.blacklisted_streams.clear()
        self.genres.clear()
        self.aliases.clear()
        self.subtitles.clear()
        self.season_episode_counts.clear()
        self.active_stream.clear()

        # Reset scalar attributes to None/defaults
        scalar_attrs = [
            'id', 'requested_at', 'requested_by', 'requested_id', 'indexed_at',
            'scraped_at', 'title', 'trakt_id', 'imdb_id', 'tvdb_id', 'tmdb_id',
            'network', 'country', 'language', 'aired_at', 'year', 'key', 'guid',
            'update_folder', 'overseerr_id', 'file', 'folder', 'symlinked_at'
        ]

        for attr in scalar_attrs:
            if hasattr(self, attr):
                setattr(self, attr, None)

        # Reset numeric/boolean attributes
        self.scraped_times = 0
        self.last_season_count = 0
        self.last_episode_count = 0
        self.symlinked_times = 0
        self.symlinked = False
        self.is_anime = False

    def _prepare_for_pool(self):
        """Prepare instance for return to object pool."""
        # Clear any database session references
        if hasattr(self, '_sa_instance_state'):
            # Expunge from session if attached
            session = object_session(self)
            if session:
                session.expunge(self)

        # Clear any circular references
        if hasattr(self, 'parent'):
            self.parent = None

    @classmethod
    def create_from_pool(cls, item: dict, item_type: str = "mediaitem") -> 'MediaItem':
        """
        Create a MediaItem instance using object pool for better performance.

        Args:
            item: Dictionary with item data
            item_type: Type of item to create ("mediaitem", "movie", "show", "season", "episode")

        Returns:
            MediaItem instance from pool or newly created
        """
        instance = _media_item_pool.get_item(item_type)
        if item:
            instance._initialize_from_dict(item)
        return instance

    def return_to_pool(self):
        """Return this instance to the object pool for reuse."""
        _media_item_pool.return_item(self)

    @staticmethod
    def get_pool_stats() -> dict:
        """Get object pool statistics."""
        return _media_item_pool.get_stats()

    @staticmethod
    def __generate_composite_key(item: dict) -> str | None:
        """Generate a composite key for the item."""
        trakt_id = item.get("trakt_id", None)
        if not trakt_id:
            return None
        item_type = item.get("type", "unknown")
        return f"{item_type}_{trakt_id}"

    def store_state(self, given_state=None) -> tuple[States, States]:
        """Store the state of the item."""
        previous_state = self.last_state
        new_state = given_state if given_state else self._determine_state()
        if previous_state and previous_state != new_state:
            websocket_manager.publish("item_update", {"last_state": previous_state, "new_state": new_state, "item_id": self.id})
        self.last_state = new_state
        return (previous_state, new_state)

    def is_stream_blacklisted(self, stream: Stream):
        """Check if a stream is blacklisted for this item."""
        session = object_session(self)
        if session:
            session.refresh(self, attribute_names=["blacklisted_streams"])
        return stream in self.blacklisted_streams

    def blacklist_active_stream(self):
        if not self.active_stream:
            logger.debug(f"No active stream for {self.log_string}, will not blacklist")
            return

        def find_and_blacklist_stream(streams):
            stream = next((s for s in streams if s.infohash == self.active_stream.get("infohash")), None)
            if stream:
                self.blacklist_stream(stream)
                logger.debug(f"Blacklisted stream {stream.infohash} for {self.log_string}")
                return True
            return False

        if find_and_blacklist_stream(self.streams):
            return

        if self.type == "episode":
            if self.parent and find_and_blacklist_stream(self.parent.streams):
                return
            if self.parent and self.parent.parent and find_and_blacklist_stream(self.parent.parent.streams):
                return

        logger.debug(f"Unable to find stream from item hierarchy for {self.log_string}, will not blacklist")

    def blacklist_stream(self, stream: Stream):
        value = blacklist_stream(self, stream)
        if value:
            logger.debug(f"Blacklisted stream {stream.infohash} for {self.log_string}")
        return value

    @property
    def is_released(self) -> bool:
        """Check if an item has been released."""
        if self.aired_at and self.aired_at <= datetime.now():
            return True
        return False

    @property
    def state(self):
        return self._determine_state()

    def _determine_state(self):
        if self.last_state == States.Paused:
            return States.Paused
        if self.last_state == States.Failed:
            return States.Failed
        if self.key or self.update_folder == "updated":
            return States.Completed
        elif self.symlinked:
            return States.Symlinked
        elif self.file and self.folder:
            return States.Downloaded
        elif self.is_scraped():
            return States.Scraped
        elif self.title and self.is_released:
            return States.Indexed
        elif self.title:
            return States.Unreleased
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

    def is_scraped(self) -> bool:
        """Check if the item has been scraped."""
        session = object_session(self)
        if session and session.is_active:
            try:
                session.refresh(self, attribute_names=["blacklisted_streams"])
                return (len(self.streams) > 0 and any(stream not in self.blacklisted_streams for stream in self.streams))
            except:
                ...
        return False

    def to_dict(self):
        """Convert item to dictionary (API response)"""
        return {
            "id": str(self.id),
            "title": self.title,
            "type": self.__class__.__name__,
            "trakt_id": self.trakt_id if hasattr(self, "trakt_id") else None,
            "imdb_id": self.imdb_id if hasattr(self, "imdb_id") else None,
            "tvdb_id": self.tvdb_id if hasattr(self, "tvdb_id") else None,
            "tmdb_id": self.tmdb_id if hasattr(self, "tmdb_id") else None,
            "state": self.last_state.name,
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

    def to_extended_dict(self, abbreviated_children=False, with_streams=True):
        """Convert item to extended dictionary (API response)"""
        dict = self.to_dict()
        match self:
            case Show():
                dict["seasons"] = (
                    [season.to_extended_dict(with_streams=with_streams) for season in self.seasons]
                    if not abbreviated_children
                    else self.represent_children
                )
            case Season():
                dict["episodes"] = (
                    [episode.to_extended_dict(with_streams=with_streams) for episode in self.episodes]
                    if not abbreviated_children
                    else self.represent_children
                )
        dict["language"] = self.language if hasattr(self, "language") else None
        dict["country"] = self.country if hasattr(self, "country") else None
        dict["network"] = self.network if hasattr(self, "network") else None
        if with_streams:
            dict["streams"] = getattr(self, "streams", [])
            dict["blacklisted_streams"] = getattr(self, "blacklisted_streams", [])
            dict["active_stream"] = (
                self.active_stream if hasattr(self, "active_stream") else None
            )
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
        dict["subtitles"] = [subtitle.to_dict() for subtitle in self.subtitles] if hasattr(self, "subtitles") else []
        return dict

    def __iter__(self):
        for attr, _ in vars(self).items():
            yield attr

    def __eq__(self, other):
        if type(other) == type(self):
            return self.id == other.id
        return False

    def copy(self, other):
        if other is None:
            return None
        self.id = getattr(other, "id", None)
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
        if self.type == "season":
            return self.parent.title
        elif self.type == "episode":
            return self.parent.parent.title
        else:
            return self.title

    def get_top_imdb_id(self) -> str:
        """Get the imdb_id of the item at the top of the hierarchy."""
        if self.type == "season":
            return self.parent.imdb_id
        elif self.type == "episode":
            return self.parent.parent.imdb_id
        return self.imdb_id

    def get_aliases(self) -> dict:
        """Get the aliases of the item."""
        if self.type == "season":
            return self.parent.aliases
        elif self.type == "episode":
            return self.parent.parent.aliases
        else:
            return self.aliases

    def __hash__(self):
        return hash(self.id)

    def reset(self):
        """Reset item attributes."""
        if self.type == "show":
            for season in self.seasons:
                for episode in season.episodes:
                    episode._reset()
                season._reset()
        elif self.type == "season":
            for episode in self.episodes:
                episode._reset()
        self._reset()
        if self.title:
            self.store_state(States.Indexed)
        else:
            self.store_state(States.Requested)

    def _reset(self):
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

        reset_streams(self)
        self.active_stream = {}

        self.set("active_stream", {})
        self.set("symlinked", False)
        self.set("symlinked_at", None)
        self.set("update_folder", None)
        self.set("scraped_at", None)
        self.set("symlinked_times", 0)
        self.set("scraped_times", 0)
        self.set("failed_attempts", 0)

        logger.debug(f"Item {self.log_string} has been reset")

    def soft_reset(self):
        """Soft reset item attributes."""
        self.blacklist_active_stream()
        self.set("file", None)
        self.set("folder", None)
        self.set("alternative_folder", None)
        self.set("active_stream", {})
        self.set("symlinked", False)
        self.set("symlinked_at", None)
        self.set("symlinked_times", 0)

    def update_show_status(self, status: str, last_air_date: datetime = None, next_air_date: datetime = None):
        """
        Update show status information for intelligent re-indexing.

        Args:
            status: Show status ("ongoing", "ended", "hiatus", "unknown")
            last_air_date: Date of last aired episode
            next_air_date: Date of next expected episode
        """
        if self.type != "show":
            return

        self.show_status = status
        if last_air_date:
            self.last_air_date = last_air_date
        if next_air_date:
            self.next_air_date = next_air_date
        self.status_last_updated = datetime.now()

    def should_check_for_updates(self) -> bool:
        """
        Determine if this show should be checked for updates based on status and air dates.
        """
        if self.type != "show":
            return False

        now = datetime.now()

        # Always check if we've never checked status before
        if not self.status_last_updated:
            return True

        # Check based on show status
        if self.show_status == "ongoing":
            # Ongoing shows: check more frequently
            if self.next_air_date and self.next_air_date <= now:
                return True  # Expected air date has passed

            # Check weekly for ongoing shows without next air date
            return (now - self.status_last_updated).days >= 7

        elif self.show_status == "ended":
            # Ended shows: check monthly (might get reboots/specials)
            return (now - self.status_last_updated).days >= 30

        elif self.show_status == "hiatus":
            # Shows on hiatus: check bi-weekly
            return (now - self.status_last_updated).days >= 14

        else:  # unknown status
            # Unknown status: check weekly to determine status
            return (now - self.status_last_updated).days >= 7

    def get_expected_update_priority(self) -> int:
        """
        Get priority score for show updates (higher = more priority).
        Used for prioritizing which shows to check first.
        """
        if self.type != "show":
            return 0

        priority = 0
        now = datetime.now()

        # Status-based priority
        if self.show_status == "ongoing":
            priority += 100
        elif self.show_status == "hiatus":
            priority += 50
        elif self.show_status == "unknown":
            priority += 75  # High priority to determine status
        else:  # ended
            priority += 10

        # Air date proximity bonus
        if self.next_air_date:
            days_until_air = (self.next_air_date - now).days
            if days_until_air <= 0:
                priority += 50  # Past due
            elif days_until_air <= 7:
                priority += 30  # Within a week
            elif days_until_air <= 30:
                priority += 15  # Within a month

        # Recent activity bonus
        if self.last_air_date:
            days_since_air = (now - self.last_air_date).days
            if days_since_air <= 30:
                priority += 25  # Recently aired
            elif days_since_air <= 90:
                priority += 15  # Moderately recent

        # Never indexed gets highest priority
        if not self.indexed_at:
            priority += 200

        return priority

    @property
    def log_string(self):
        return self.title or self.id

    @property
    def collection(self):
        return self.parent.collection if self.parent else self.id

    def is_parent_blocked(self) -> bool:
        """
        Check if any parent is paused.

        A paused item blocks all processing of itself and its children,
        typically set by user action from the frontend.
        """
        if self.last_state == States.Paused:
            return True
            
        session = object_session(self)
        if session and hasattr(self, "parent"):
            session.refresh(self, ["parent"])
            if self.parent:
                return self.parent.is_parent_blocked()
        return False

    def get_blocking_parent(self) -> Optional["MediaItem"]:
        """
        Get the parent that is paused and blocking this item (if any).

        Returns:
            MediaItem | None: The parent in a Paused state,
                            or None if no parent is paused.
        """
        if self.last_state == States.Paused:
            return self
            
        session = object_session(self)
        if session and hasattr(self, "parent"):
            session.refresh(self, ["parent"])
            if self.parent:
                return self.parent.get_blocking_parent()
        return None


class Movie(MediaItem):
    """Movie class"""
    __tablename__ = "Movie"
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id"), primary_key=True)
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

    def __repr__(self):
        return f"Movie:{self.log_string}:{self.state.name}"

    def __hash__(self):
        return super().__hash__()

class Show(MediaItem):
    """Show class"""
    __tablename__ = "Show"
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id"), primary_key=True)
    seasons: Mapped[List["Season"]] = relationship(back_populates="parent", foreign_keys="Season.parent_id", lazy="joined", cascade="all, delete-orphan", order_by="Season.number")

    __mapper_args__ = {
        "polymorphic_identity": "show",
        "polymorphic_load": "inline",
    }

    def __init__(self, item):
        self.type = "show"
        self.locations = item.get("locations", [])
        self.seasons: list[Season] = item.get("seasons", [])
        self.propagate_attributes_to_childs()
        super().__init__(item)

    def get_season_index_by_id(self, item_id):
        """Find the index of an season by its _id."""
        for i, season in enumerate(self.seasons):
            if season.id == item_id:
                return i
        return None

    def _determine_state(self):
        if all(season.state == States.Paused for season in self.seasons):
            return States.Paused
        if all(season.state == States.Failed for season in self.seasons):
            return States.Failed
        if all(season.state == States.Completed for season in self.seasons):
            return States.Completed
        if any(season.state in [States.Ongoing, States.Unreleased] for season in self.seasons):
            return States.Ongoing
        if any(
            season.state in (States.Completed, States.PartiallyCompleted)
            for season in self.seasons
        ):
            return States.PartiallyCompleted
        if any(season.state == States.Symlinked for season in self.seasons):
            return States.Symlinked
        if any(season.state == States.Downloaded for season in self.seasons):
            return States.Downloaded
        if self.is_scraped():
            return States.Scraped
        if any(season.state == States.Indexed for season in self.seasons):
            return States.Indexed
        if all(not season.is_released for season in self.seasons):
            return States.Unreleased
        if any(season.state == States.Requested for season in self.seasons):
            return States.Requested
        return States.Unknown

    def store_state(self, given_state: States = None) -> None:
        for season in self.seasons:
            season.store_state(given_state)
        super().store_state(given_state)

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

    def get_episode(self, episode_number: int, season_number: int = None) -> Optional["Episode"]:
        """Get the absolute episode number based on season and episode."""
        if not episode_number or episode_number == 0:
            return None

        if season_number is not None:
            season = next((s for s in self.seasons if s.number == season_number), None)
            if season:
                episode = next((e for e in season.episodes if e.number == episode_number), None)
                if episode:
                    return episode

        episode_count = 0
        for season in self.seasons:
            for episode in season.episodes:
                episode_count += 1
                if episode_count == episode_number:
                    return episode

        return None

class Season(MediaItem):
    """Season class"""
    __tablename__ = "Season"
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id"), primary_key=True)
    parent_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("Show.id"), use_existing_column=True)
    parent: Mapped["Show"] = relationship(lazy="select", back_populates="seasons", foreign_keys="Season.parent_id")
    episodes: Mapped[List["Episode"]] = relationship(back_populates="parent", foreign_keys="Episode.parent_id", lazy="joined", cascade="all, delete-orphan", order_by="Episode.number")
    __mapper_args__ = {
        "polymorphic_identity": "season",
        "polymorphic_load": "inline",
    }

    def store_state(self, given_state: States = None) -> None:
        for episode in self.episodes:
            episode.store_state(given_state)
        super().store_state(given_state)

    def __init__(self, item):
        self.type = "season"
        self.number = item.get("number", None)
        self.episodes: list[Episode] = item.get("episodes", [])
        super().__init__(item)
        if self.parent and isinstance(self.parent, Show):
            self.is_anime = self.parent.is_anime

    def _determine_state(self):
        if len(self.episodes) > 0:
            if all(episode.state == States.Paused for episode in self.episodes):
                return States.Paused
            if all(episode.state == States.Failed for episode in self.episodes):
                return States.Failed
            if all(episode.state == States.Completed for episode in self.episodes):
                return States.Completed
            if any(episode.state == States.Unreleased for episode in self.episodes):
                if any(episode.state != States.Unreleased for episode in self.episodes):
                    return States.Ongoing
            if any(episode.state == States.Completed for episode in self.episodes):
                return States.PartiallyCompleted
            if any(episode.state == States.Symlinked for episode in self.episodes):
                return States.Symlinked
            if any(episode.file and episode.folder for episode in self.episodes):
                return States.Downloaded
            if self.is_scraped():
                return States.Scraped
            if any(episode.state == States.Indexed for episode in self.episodes):
                return States.Indexed
            if any(episode.state == States.Unreleased for episode in self.episodes):
                return States.Unreleased
            if any(episode.state == States.Requested for episode in self.episodes):
                return States.Requested
            return States.Unknown
        else:
            return States.Unreleased

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

    def get_episode_index_by_id(self, item_id: int):
        """Find the index of an episode by its _id."""
        for i, episode in enumerate(self.episodes):
            if episode.id == item_id:
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
        """Get the top title of the season."""
        session = object_session(self)
        if session:
            session.refresh(self, ["parent"])
        return self.parent.title


class Episode(MediaItem):
    """Episode class"""
    __tablename__ = "Episode"
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id"), primary_key=True)
    parent_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("Season.id"), use_existing_column=True)
    parent: Mapped["Season"] = relationship(back_populates="episodes", foreign_keys="Episode.parent_id", lazy="select")

    __mapper_args__ = {
        "polymorphic_identity": "episode",
        "polymorphic_load": "inline",
    }

    def __init__(self, item):
        self.type = "episode"
        self.number = item.get("number", None)
        self.file = item.get("file", None)
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
        return parse_title(self.file)["episodes"]

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