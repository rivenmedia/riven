"""MediaItem class"""
from datetime import datetime
from typing import Any, List, Optional, Self, TYPE_CHECKING

import sqlalchemy
from loguru import logger
from PTT import parse_title
from sqlalchemy import Index, exists, select
from sqlalchemy.orm import Mapped, aliased, mapped_column, object_session, relationship

from program.db.db import db
from program.managers.websocket_manager import manager as websocket_manager
from program.media.state import States
from program.media.subtitle import Subtitle

from ..db.db_functions import clear_streams, set_stream_blacklisted
from .stream import Stream, StreamBlacklistRelation, StreamRelation

if TYPE_CHECKING:
    from program.media.filesystem_entry import FilesystemEntry


class MediaItem(db.Model):
    """MediaItem class"""
    __tablename__ = "MediaItem"
    id: Mapped[str] = mapped_column(sqlalchemy.String, primary_key=True)
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
    active_stream: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, nullable=True)
    streams: Mapped[list[Stream]] = relationship(secondary="StreamRelation", back_populates="parents", lazy="selectin", cascade="all")
    blacklisted_streams: Mapped[list[Stream]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_parents", lazy="selectin", cascade="all")

    aliases: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, default={})
    is_anime: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    network: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    aired_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    genres: Mapped[Optional[List[str]]] = mapped_column(sqlalchemy.JSON, nullable=True)
    updated: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    guid: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    overseerr_id: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    last_state: Mapped[Optional[States]] = mapped_column(sqlalchemy.Enum(States), default=States.Unknown)
    subtitles: Mapped[list[Subtitle]] = relationship(Subtitle, back_populates="parent", lazy="selectin", cascade="all, delete-orphan", passive_deletes=True)
    failed_attempts: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)

    filesystem_entry_id: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, sqlalchemy.ForeignKey("FilesystemEntry.id"), nullable=True)
    filesystem_entry: Mapped[Optional["FilesystemEntry"]] = relationship("FilesystemEntry", back_populates="media_items", lazy="selectin")

    __mapper_args__ = {
        "polymorphic_identity": "mediaitem",
        "polymorphic_on":"type",
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
        self.id = self.__generate_composite_key(item)

        self.requested_at = item.get("requested_at", datetime.now())
        self.requested_by = item.get("requested_by")
        self.requested_id = item.get("requested_id")

        self.indexed_at = None

        self.scraped_at  = None
        self.scraped_times = 0
        self.active_stream = item.get("active_stream", {})
        self.streams: List[Stream] = []
        self.blacklisted_streams: List[Stream] = []

        # Media related
        self.title = item.get("title")
        self.imdb_id = item.get("imdb_id")
        self.tvdb_id = item.get("tvdb_id")
        self.tmdb_id = item.get("tmdb_id")
        self.network = item.get("network")
        self.country = item.get("country")
        self.language = item.get("language")
        self.aired_at = item.get("aired_at")
        self.year = item.get("year")
        self.genres = item.get("genres", [])
        self.aliases = item.get("aliases", {})
        self.is_anime = item.get("is_anime", False)

        # Media server related
        self.updated = item.get("updated", False)
        self.guid = item.get("guid")

        # Overseerr related
        self.overseerr_id = item.get("overseerr_id")

        # Post-processing
        self.subtitles = item.get("subtitles", [])

    @staticmethod
    def __generate_composite_key(item: dict) -> str | None:
        """Generate a composite key for the item."""
        item_type = item.get("type", "unknown")

        if item_type == "movie":
            if tmdb_id := item.get("tmdb_id"):
                return f"tmdb_movie_{tmdb_id}"

        elif item_type in ["show", "season", "episode"]:
            if tvdb_id := item.get("tvdb_id"):
                return f"tvdb_{item_type}_{tvdb_id}"

        # For generic media items, try to determine type
        elif item_type == "mediaitem":
            if item.get("seasons") or hasattr(item, "seasons"):
                if tvdb_id := item.get("tvdb_id"):
                    return f"tvdb_show_{tvdb_id}"
            elif tmdb_id := item.get("tmdb_id"):
                return f"tmdb_movie_{tmdb_id}"

        return None

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
            # Avoid triggering autoflush while refreshing relationships
            with session.no_autoflush:
                session.refresh(self, attribute_names=["blacklisted_streams"])
        return stream in self.blacklisted_streams

    def blacklist_active_stream(self) -> bool:
        if not self.active_stream:
            logger.debug(f"No active stream for {self.log_string}, will not blacklist")
            return False

        def find_and_blacklist_stream(streams):
            stream = next((s for s in streams if s.infohash == self.active_stream.get("infohash")), None)
            if stream:
                self.blacklist_stream(stream)
                logger.debug(f"Blacklisted stream {stream.infohash} for {self.log_string}")
                return True
            return False

        if find_and_blacklist_stream(self.streams):
            return True

        if self.type == "episode":
            if self.parent and find_and_blacklist_stream(self.parent.streams):
                return True
            if self.parent and self.parent.parent and find_and_blacklist_stream(self.parent.parent.streams):
                return True

        logger.debug(f"Unable to find stream from item hierarchy for {self.log_string}, will not blacklist")
        return False

    def blacklist_stream(self, stream: Stream) -> bool:
        value = set_stream_blacklisted(self, stream, blacklisted=True)
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
    def state(self) -> States:
        return self._determine_state()

    def _determine_state(self) -> States:
        if self.last_state == States.Paused:
            return States.Paused
        if self.last_state == States.Failed:
            return States.Failed
        if self.updated:
            return States.Completed
        elif self.available_in_vfs:
            # Consider Symlinked (available) when VFS has the entry mounted
            return States.Symlinked
        elif self.filesystem_entry:
            # Downloaded if we have filesystem_entry (from downloader)
            return States.Downloaded
        elif self.is_scraped():
            return States.Scraped
        elif self.title and self.is_released:
            return States.Indexed
        elif self.title:
            return States.Unreleased
        elif (self.imdb_id or self.tmdb_id or self.tvdb_id) and self.requested_by:
            return States.Requested
        return States.Unknown

    def copy_other_media_attr(self, other) -> None:
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
        """Check if the item has at least one non-blacklisted stream using a targeted EXISTS query."""
        s = object_session(self)
        if not s:
            return False
        try:
            q = select(
                exists().where(
                    StreamRelation.parent_id == self.id,
                ).where(
                    ~exists().where(
                        StreamBlacklistRelation.media_item_id == self.id,
                    ).where(
                        StreamBlacklistRelation.stream_id == StreamRelation.child_id
                    )
                )
            )
            return bool(s.execute(q).scalar())
        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        """Convert item to dictionary (API response)"""
        parent_title = self.title
        season_number = None
        episode_number = None
        parent_ids = {
            "trakt_id": self.tmdb_id if hasattr(self, "tmdb_id") else None,
            "imdb_id": self.imdb_id if hasattr(self, "imdb_id") else None,
            "tvdb_id": self.tvdb_id if hasattr(self, "tvdb_id") else None,
            "tmdb_id": self.tvdb_id if hasattr(self, "tvdb_id") else None
        }

        if self.type == "season":
            parent_title = self.parent.title
            season_number = self.number
            parent_ids["trakt_id"] = self.parent.trakt_id if hasattr(self, "parent") and hasattr(self.parent, "trakt_id") else None
            parent_ids["imdb_id"] = self.parent.imdb_id if hasattr(self, "parent") and hasattr(self.parent, "imdb_id") else None
            parent_ids["tvdb_id"] = self.parent.tvdb_id if hasattr(self, "parent") and hasattr(self.parent, "tvdb_id") else None
            parent_ids["tmdb_id"] = self.parent.tmdb_id if hasattr(self, "parent") and hasattr(self.parent, "tmdb_id") else None
        elif self.type == "episode":
            parent_title = self.parent.parent.title
            season_number = self.parent.number
            episode_number = self.number
            parent_ids["trakt_id"] = self.parent.parent.trakt_id if hasattr(self, "parent") and hasattr(self.parent, "trakt_id") else None
            parent_ids["imdb_id"] = self.parent.parent.imdb_id if hasattr(self, "parent") and hasattr(self.parent, "parent") and hasattr(self.parent.parent, "imdb_id") else None
            parent_ids["tvdb_id"] = self.parent.parent.tvdb_id if hasattr(self, "parent") and hasattr(self.parent, "parent") and hasattr(self.parent.parent, "tvdb_id") else None
            parent_ids["tmdb_id"] = self.parent.parent.tmdb_id if hasattr(self, "parent") and hasattr(self.parent, "parent") and hasattr(self.parent.parent, "tmdb_id") else None

        data = {
            "id": str(self.id),
            "title": self.title,
            "type": self.__class__.__name__,
            "parent_title": parent_title,
            "season_number": season_number,
            "episode_number": episode_number,
            "imdb_id": self.imdb_id if hasattr(self, "imdb_id") else None,
            "tvdb_id": self.tvdb_id if hasattr(self, "tvdb_id") else None,
            "tmdb_id": self.tmdb_id if hasattr(self, "tmdb_id") else None,
            "parent_ids": parent_ids,
            "state": self.last_state.name if self.last_state else self.state.name,
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

        if hasattr(self, "seasons") or hasattr(self, "episodes"):
            data["parent_ids"] = parent_ids

        return data

    def to_extended_dict(self, abbreviated_children=False, with_streams=False) -> dict[str, Any]:
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
        dict["is_anime"] = self.is_anime if hasattr(self, "is_anime") else None

        dict["filesystem_entry"] = self.filesystem_entry.to_dict() if self.filesystem_entry else None
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

    # Filesystem entry properties
    @property
    def filesystem_path(self) -> Optional[str]:
        """Get the filesystem path"""
        return self.filesystem_entry.path if self.filesystem_entry else None

    @property
    def available_in_vfs(self) -> bool:
        """Whether this item is available in the mounted VFS (safe, handles None)."""
        return self.filesystem_entry and self.filesystem_entry.available_in_vfs

    @property
    def mounted_vfs_path(self) -> Optional[str]:
        """Absolute path in the mounted VFS if available, else None"""
        if self.available_in_vfs:
            from program.settings.manager import settings_manager as _sm
            mount = _sm.settings.filesystem.library_path
            return str(mount / self.filesystem_entry.path.lstrip('/'))
        return None

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
        # Remove filesystem entry if it exists
        if self.filesystem_entry:
            from program.services.filesystem.filesystem_service import FilesystemService
            from program.program import program
            filesystem_service = program.services.get(FilesystemService)
            if filesystem_service:
                filesystem_service.delete_item_files_by_id(self.id)

        try:
            for subtitle in self.subtitles:
                subtitle.remove()
        except Exception as e:
            logger.warning(f"Failed to remove subtitles for {self.log_string}: {str(e)}")

        clear_streams(self)
        self.active_stream = {}

        self.set("active_stream", {})

        self.set("scraped_at", None)
        self.set("scraped_times", 0)
        self.set("failed_attempts", 0)

        logger.debug(f"Item {self.log_string} has been reset")

    def soft_reset(self):
        """Soft reset item attributes."""
        self.blacklist_active_stream()
        self.set("active_stream", {})
        # Remove filesystem entry if it exists
        if self.filesystem_entry:
            from program.services.filesystem.filesystem_service import FilesystemService
            from program.program import program
            filesystem_service = program.services.get(FilesystemService)
            if filesystem_service:
                filesystem_service.delete_item_files_by_id(self.id)

    @property
    def log_string(self):
        if not self.title or not self.id:
            if self.tmdb_id and not self.imdb_id:
                return f"TMDB ID {self.tmdb_id}"
            elif self.tvdb_id and not self.tmdb_id:
                return f"TVDB ID {self.tvdb_id}"
            elif self.imdb_id and (not self.tmdb_id or not self.tvdb_id):
                return f"IMDB ID {self.imdb_id}"
        return self.title or self.id

    @property
    def collection(self):
        return self.parent.collection if self.parent else self.id

    def is_parent_blocked(self) -> bool:
        """Return True if self or any parent is paused using targeted lookups (no relationship refresh)."""
        if self.last_state == States.Paused:
            return True

        session = object_session(self)
        if session and hasattr(self, "parent"):
            session.refresh(self, ["parent"])
            if self.parent:
                return self.parent.is_parent_blocked()
        return False

    def get_blocking_parent(self) -> Optional["MediaItem"]:
        """Return the nearest paused ancestor (self, parent season, or parent show), or None."""
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
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True)
    __mapper_args__ = {
        "polymorphic_identity": "movie",
        "polymorphic_load": "selectin",
    }

    def copy(self, other):
        super().copy(other)
        return self

    def __init__(self, item):
        self.type = "movie"
        super().__init__(item)

    def __repr__(self):
        return f"Movie:{self.log_string}:{self.state.name}"

    def __hash__(self):
        return super().__hash__()

class Show(MediaItem):
    """Show class"""
    __tablename__ = "Show"
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True)
    seasons: Mapped[List["Season"]] = relationship(
        back_populates="parent",
        foreign_keys="Season.parent_id",
        lazy="joined",
        cascade="all, delete-orphan",
        order_by="Season.number",
        passive_deletes=True, # don't pre-load children on delete
    )
    release_data: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, default={})

    __mapper_args__ = {
        "polymorphic_identity": "show",
        "polymorphic_load": "selectin",
    }

    def __init__(self, item):
        self.type = "show"
        self.locations = item.get("locations", [])
        self.seasons: list[Season] = item.get("seasons", [])
        self.release_data = item.get("release_data", {})
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

    def store_state(self, given_state: States = None) -> tuple[States, States]:
        for season in self.seasons:
            season.store_state(given_state)
        return super().store_state(given_state)

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

    def get_absolute_episode(self, episode_number: int, season_number: int = None) -> Optional["Episode"]:
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
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True)
    parent_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("Show.id", ondelete="CASCADE"), use_existing_column=True)
    parent: Mapped["Show"] = relationship(
        lazy=False,
        back_populates="seasons",
        foreign_keys="Season.parent_id",
        passive_deletes=True, # avoid ORM deletes doing SELECTs
    )
    episodes: Mapped[List["Episode"]] = relationship(
        back_populates="parent",
        foreign_keys="Episode.parent_id",
        lazy="joined",
        cascade="all, delete-orphan",
        order_by="Episode.number",
        passive_deletes=True, # avoid ORM deletes doing SELECTs
    )
    __mapper_args__ = {
        "polymorphic_identity": "season",
        "polymorphic_load": "selectin",
    }

    def store_state(self, given_state: States = None) -> tuple[States, States]:
        for episode in self.episodes:
            episode.store_state(given_state)
        return super().store_state(given_state)

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
            if any(episode.state == States.Downloaded for episode in self.episodes):
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
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True)
    parent_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("Season.id", ondelete="CASCADE"), use_existing_column=True)
    parent: Mapped["Season"] = relationship(
        back_populates="episodes",
        foreign_keys="Episode.parent_id",
        lazy="joined",
        passive_deletes=True, # avoid ORM deletes doing SELECTs
    )
    absolute_number: Mapped[int] = mapped_column(sqlalchemy.Integer, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "episode",
        "polymorphic_load": "selectin",
    }

    def __init__(self, item):
        self.type = "episode"
        self.number = item.get("number", None)
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
        if not self.filesystem_entry or not self.filesystem_entry.original_filename:
            raise ValueError("The filesystem entry must have an original filename.")
        # return list of episodes
        return parse_title(self.filesystem_entry.original_filename)["episodes"]

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