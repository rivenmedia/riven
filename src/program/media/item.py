"""
MediaItem models for Riven.

This module defines the MediaItem hierarchy:
- MediaItem: Base class for all media (movies, shows, seasons, episodes)
- Movie: Individual movie
- Show: TV show (contains seasons)
- Season: TV season (contains episodes)
- Episode: Individual TV episode

MediaItems contain profile-agnostic metadata from indexers (IMDb, TMDB, TVDB).
Profile-specific downloads are stored in MediaEntry instances (one per scraping profile).
"""
from datetime import datetime
from typing import Any, List, Optional, TYPE_CHECKING

import sqlalchemy
from loguru import logger
from PTT import parse_title
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from program.db.db import db
from program.media.state import States
from program.media.entry_state import EntryState

from .stream import Stream

if TYPE_CHECKING:
    from program.media.filesystem_entry import FilesystemEntry


class MediaItem(db.Model):
    """
    Base model for all media items (movies, shows, seasons, episodes).

    MediaItem stores profile-agnostic metadata from indexers (IMDb, TMDB, TVDB).
    Each MediaItem can have multiple MediaEntry instances (one per scraping profile)
    representing different downloaded versions.

    Attributes:
        id: Primary key (integer).
        imdb_id: IMDb identifier.
        tvdb_id: TVDB identifier.
        tmdb_id: TMDB identifier.
        title: Media title.
        number: Episode/season number (for episodes/seasons).
        type: Discriminator for polymorphic identity (movie/show/season/episode).
        requested_at: When the item was requested.
        requested_by: Who requested the item (service name).
        requested_id: External request ID (e.g., Overseerr request ID).
        indexed_at: When metadata was fetched from indexer.
        scraped_at: When streams were last scraped.
        scraped_times: Number of times item has been scraped.
        streams: All discovered streams (shared across profiles).
        blacklisted_streams: Streams that failed and should be avoided.
        aliases: Alternative titles for matching.
        is_anime: Whether this is anime content.
        network: TV network (for shows).
        country: Country of origin.
        language: Primary language.
        aired_at: When the content first aired.
        year: Release year.
        genres: List of genre strings.
        updated: Whether media server has processed this item.
        guid: Media server GUID.
        overseerr_id: Overseerr request ID.
        last_state: Current state in the state machine.
        failed_attempts: Number of failed processing attempts.
        filesystem_entries: List of FilesystemEntry instances (MediaEntry, SubtitleEntry).
    """
    __tablename__ = "MediaItem"
    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tvdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tmdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    number: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    type: Mapped[str] = mapped_column(sqlalchemy.String, nullable=False)
    # Request/Scraping tracking (item-level metadata)
    requested_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, default=datetime.now())
    requested_by: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    requested_id: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    scraped_times: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)

    # Streams (all discovered streams for this item, shared across profiles)
    streams: Mapped[list[Stream]] = relationship(secondary="StreamRelation", back_populates="parents", lazy="selectin", cascade="all")
    blacklisted_streams: Mapped[list[Stream]] = relationship(secondary="StreamBlacklistRelation", back_populates="blacklisted_parents", lazy="selectin", cascade="all")

    # Indexer metadata
    aliases: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, default={})
    is_anime: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    network: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    country: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    aired_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)
    genres: Mapped[Optional[List[str]]] = mapped_column(sqlalchemy.JSON, nullable=True)

    # Media server related
    updated: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    guid: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    overseerr_id: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, nullable=True)

    # State tracking
    last_state: Mapped[Optional[States]] = mapped_column(sqlalchemy.Enum(States), default=States.Unknown)
    failed_attempts: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)

    # Relationships
    filesystem_entries: Mapped[list["FilesystemEntry"]] = relationship(
        "FilesystemEntry",
        back_populates="media_item",
        lazy="selectin",
        cascade="all, delete-orphan"
    )

    # Note: active_stream and parsed_data removed - these are now per-MediaEntry
    # Note: subtitles relationship removed - subtitles now relate to MediaEntry

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
        """
        Initialize a MediaItem from a dictionary.

        Args:
            item: Dictionary containing item metadata from indexer or content service.
                  Can be None for SQLAlchemy internal use.
        """
        if item is None:
            return

        # Request tracking
        self.requested_at = item.get("requested_at", datetime.now())
        self.requested_by = item.get("requested_by")
        self.requested_id = item.get("requested_id")

        # Scraping tracking
        self.indexed_at = None
        self.scraped_at = None
        self.scraped_times = 0

        # Streams
        self.streams: List[Stream] = []
        self.blacklisted_streams: List[Stream] = []

        # Indexer metadata
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
        self.guid = item.get("guid")

        # Overseerr related
        self.overseerr_id = item.get("overseerr_id")

    def store_state(self, given_state=None) -> tuple[States, States]:
        """
        Store the current state and trigger notifications if state changed.

        Args:
            given_state: Optional state to set explicitly. If None, state is determined automatically.

        Returns:
            tuple[States, States]: (previous_state, new_state)
        """
        previous_state = self.last_state
        new_state = given_state if given_state else self._determine_state()
        if previous_state and previous_state != new_state:
            from program.program import riven
            from program.services.notifier import Notifier
            riven.services[Notifier].run(self)
        self.last_state = new_state
        return (previous_state, new_state)

    @property
    def is_released(self) -> bool:
        """
        Check if an item has been released (aired).

        Returns:
            bool: True if aired_at is in the past, False otherwise.
        """
        if self.aired_at and self.aired_at <= datetime.now():
            return True
        return False

    @property
    def state(self) -> States:
        """
        Get the current state of this MediaItem.

        Returns:
            States: The computed state based on current attributes.
        """
        return self._determine_state()

    def _determine_state(self) -> States:
        """
        Determine the current state of this MediaItem based on its attributes
        and the state of its MediaEntry instances across all scraping profiles.

        State priority (for Movies/Episodes only):
        1. Paused/Failed - explicit states that override everything
        2. Completed - item processed by media server
        3. Symlinked - at least one entry available in VFS
        4. Downloaded - at least one entry downloaded
        5. Scraped - streams available but no successful downloads
        6. Indexed - item has metadata and is released
        7. Unreleased - item has metadata but not yet aired
        8. Requested - item requested but no metadata yet
        9. Unknown - default state

        Note: Shows/Seasons override this method with simpler logic.
        """
        # Explicit states override everything
        if self.last_state == States.Paused:
            return States.Paused
        
        if self.last_state == States.Failed:
            return States.Failed
        if self.filesystem_entries:
            if all(entry.state == EntryState.Completed for entry in self.filesystem_entries if entry.entry_type == "media"):
                return States.Completed
            
            if any(entry.state == EntryState.Completed for entry in self.filesystem_entries if entry.entry_type == "media"):
                return States.PartiallyCompleted
            
            if all(entry.state == EntryState.Available for entry in self.filesystem_entries if entry.entry_type == "media"):
                return States.Available
            
            if any(entry.state == EntryState.Available for entry in self.filesystem_entries if entry.entry_type == "media"):
                return States.PartiallyAvailable
            
            if all(entry.state == EntryState.Downloaded for entry in self.filesystem_entries if entry.entry_type == "media"):
                return States.Downloaded
            
            if any(entry.state == EntryState.Downloaded for entry in self.filesystem_entries if entry.entry_type == "media"):
                return States.PartiallyDownloaded

        # No successful downloads, check if we have streams
        if self.is_scraped():
            return States.Scraped

        # Item has metadata
        if self.title and self.is_released:
            return States.Indexed
        elif self.title:
            return States.Unreleased

        # Item was requested but no metadata yet
        if (self.imdb_id or self.tmdb_id or self.tvdb_id) and self.requested_by:
            return States.Requested

        return States.Unknown

    def is_scraped(self) -> bool:
        """Check if the item has been scraped."""
        return self.streams

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
        """
        Convert item to extended dictionary (API response).

        Now includes all MediaEntry instances (one per scraping profile) instead
        of a single filesystem_entry.
        """
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
            dict["streams"] = [stream.to_dict() for stream in getattr(self, "streams", [])]
            dict["blacklisted_streams"] = [stream.to_dict() for stream in getattr(self, "blacklisted_streams", [])]
        dict["number"] = self.number if hasattr(self, "number") else None
        dict["is_anime"] = self.is_anime if hasattr(self, "is_anime") else None

        # Include all MediaEntry instances (one per scraping profile)
        from program.media.media_entry import MediaEntry
        media_entries = [e for e in self.filesystem_entries if isinstance(e, MediaEntry)]
        dict["media_entries"] = [entry.to_dict() for entry in media_entries]

        # Subtitles are now per-MediaEntry, so collect from all entries
        all_subtitles = []
        for entry in media_entries:
            if hasattr(entry, 'subtitles') and entry.subtitles:
                all_subtitles.extend([sub.to_dict() for sub in entry.subtitles])
        dict["subtitles"] = all_subtitles

        return dict

    def __iter__(self):
        """Iterate over attribute names."""
        for attr, _ in vars(self).items():
            yield attr

    def __eq__(self, other):
        """
        Check equality based on ID.

        Args:
            other: Object to compare with.

        Returns:
            bool: True if same type and same ID, False otherwise.
        """
        if type(other) == type(self):
            return self.id == other.id
        return False

    def copy(self, other):
        """
        Copy ID and number from another item.

        Args:
            other: Item to copy from.

        Returns:
            MediaItem: Self for chaining, or None if other is None.
        """
        if other is None:
            return None
        self.id = getattr(other, "id", None)
        if hasattr(self, "number"):
            self.number = getattr(other, "number", None)
        return self

    def get(self, key, default=None):
        """
        Get item attribute by key.

        Args:
            key: Attribute name.
            default: Default value if attribute doesn't exist.

        Returns:
            Any: Attribute value or default.
        """
        return getattr(self, key, default)

    def set(self, key, value):
        """
        Set item attribute by key.

        Args:
            key: Attribute name (supports nested attributes with dots).
            value: Value to set.
        """
        _set_nested_attr(self, key, value)

    def get_top_title(self) -> str:
        """
        Return the top-level title for this media item.
        
        Returns:
            str: The show's title for seasons and episodes (parent for season, grandparent for episode); otherwise the item's own title.
        """
        if self.type == "season":
            return self.parent.title
        elif self.type == "episode":
            return self.parent.parent.title
        else:
            return self.title

    def get_top_imdb_id(self) -> str:
        """
        Return the IMDb identifier for the top-level item in the hierarchy.
        
        Returns:
            imdb_id (str | None): IMDb identifier string from the show (top-level) when this item is a season or episode; otherwise the item's own `imdb_id`. May be `None` if no identifier is set.
        """
        if self.type == "season":
            return self.parent.imdb_id
        elif self.type == "episode":
            return self.parent.parent.imdb_id
        return self.imdb_id

    def get_aliases(self) -> dict:
        """
        Get the aliases for this item.

        For seasons/episodes, returns the parent show's aliases.

        Returns:
            dict: Dictionary of alternative titles for matching.
        """
        if self.type == "season":
            return self.parent.aliases
        elif self.type == "episode":
            return self.parent.parent.aliases
        else:
            return self.aliases

    def __hash__(self):
        """Hash based on ID for use in sets/dicts."""
        return hash(self.id)

    def reset(self):
        """
        Reset this item's internal state and recursively reset child items when applicable.
        
        For a show, resets all seasons and their episodes; for a season, resets its episodes. After child resets, resets this item and updates its stored state.
        """
        if self.type == "show":
            for season in self.seasons:
                for episode in season.episodes:
                    episode._reset()
                season._reset()
        elif self.type == "season":
            for episode in self.episodes:
                episode._reset()
        self._reset()
        self.store_state()

    def _reset(self):
        """
        Reset the media item and its related associations to prepare for rescraping.
        
        Clears filesystem entries, subtitles, active and related streams, and resets scraping-related metadata (updated, scraped_at, scraped_times, failed_attempts). ORM cascade and configured event listeners are relied upon to delete associated records and perform filesystem/VFS cleanup where applicable.
        """
        # Clear filesystem entries - ORM automatically deletes orphaned entries
        self.filesystem_entries.clear()

        # Clear streams using ORM relationship operations (database CASCADE handles orphans)
        self.streams.clear()
        self.active_stream = {}

        # Reset scraping metadata
        self.updated = False
        self.parsed_data = {}
        self.scraped_at = None
        self.scraped_times = 0
        self.failed_attempts = 0

        logger.debug(f"Item {self.log_string} has been reset")

    @property
    def log_string(self):
        """
        Generate a human-readable log string for this item.

        Returns:
            str: Title if available, otherwise ID or external IDs, or "Unknown".
        """
        if self.title:
            return self.title
        elif self.id:
            return f"Item ID {self.id}"
        elif self.tmdb_id and not self.imdb_id:
            return f"TMDB ID {self.tmdb_id}"
        elif self.tvdb_id and not self.tmdb_id:
            return f"TVDB ID {self.tvdb_id}"
        elif self.imdb_id and (not self.tmdb_id and not self.tvdb_id):
            return f"IMDB ID {self.imdb_id}"
        return "Unknown"

    @property
    def collection(self):
        """
        Get the collection ID for this item.

        Returns:
            int: Parent's collection if this has a parent, otherwise own ID.
        """
        return self.parent.collection if self.parent else self.id

    def is_parent_blocked(self) -> bool:
        """
        Check if this item or any parent is paused.

        Recursively checks parent hierarchy for Paused state.

        Returns:
            bool: True if this item or any parent is paused, False otherwise.
        """
        if self.last_state == States.Paused:
            return True

        session = object_session(self)
        if session and hasattr(self, "parent"):
            session.refresh(self, ["parent"])
            if self.parent:
                return self.parent.is_parent_blocked()
        return False


class Movie(MediaItem):
    """
    Movie model.

    Represents a single movie. Movies go through the full download pipeline:
    Requested → Indexed → Scraped → Downloaded → Available → Completed
    """
    __tablename__ = "Movie"
    id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True)
    __mapper_args__ = {
        "polymorphic_identity": "movie",
        "polymorphic_load": "selectin",
    }

    def copy(self, other):
        """Copy ID from another movie."""
        super().copy(other)
        return self

    def __init__(self, item):
        """Initialize a Movie from a dictionary."""
        self.type = "movie"
        super().__init__(item)

    def __repr__(self):
        """String representation of the Movie."""
        return f"Movie:{self.log_string}:{self.state.name}"

    def __hash__(self):
        """Hash based on ID."""
        return super().__hash__()

class Show(MediaItem):
    """
    TV Show model.

    Represents a TV show containing seasons.
    Individual episodes are enqueued for download after scraping.
    """
    __tablename__ = "Show"
    id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True)
    seasons: Mapped[List["Season"]] = relationship(
        back_populates="parent",
        foreign_keys="Season.parent_id",
        lazy="joined",
        cascade="all, delete-orphan",
        order_by="Season.number",
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

    def _determine_state(self):
        """
        Determine Show state based on season/episode states.

        Shows only go through: Requested → Indexed → Scraped → Ongoing/Completed/Failed
        Shows never have Downloaded/Symlinked states (only episodes do).
        """
        # Explicit states override everything
        if self.last_state == States.Paused:
            return States.Paused
        if self.last_state == States.Failed:
            return States.Failed
        
        # Any season has episodes in progress (some completed, some not)
        if any(season.state in [States.Ongoing, States.Unreleased] for season in self.seasons):
            return States.Ongoing

        # All seasons completed
        if all(season.state == States.Completed for season in self.seasons):
            return States.Completed
        
        # Some seasons completed
        if any(season.state in [States.Completed, States.PartiallyCompleted] for season in self.seasons):
            return States.PartiallyCompleted
        
        if any(season.state in [States.Available, States.PartiallyAvailable] for season in self.seasons):
            return States.PartiallyAvailable
        
        if any(season.state in [States.Downloaded, States.PartiallyDownloaded] for season in self.seasons):
            return States.PartiallyDownloaded

        # Show has been scraped
        if self.is_scraped():
            return States.Scraped

        # Show has been indexed
        if any(season.state == States.Indexed for season in self.seasons):
            return States.Indexed

        # All seasons unreleased
        if all(not season.is_released for season in self.seasons):
            return States.Unreleased

        # Show was requested
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
    """
    TV Season model.

    Represents a TV season containing episodes.
    Individual episodes are enqueued for download after scraping.
    """
    __tablename__ = "Season"
    id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True)
    parent_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Show.id", ondelete="CASCADE"), use_existing_column=True)
    parent: Mapped["Show"] = relationship(
        lazy=False,
        back_populates="seasons",
        foreign_keys="Season.parent_id",
    )
    episodes: Mapped[List["Episode"]] = relationship(
        back_populates="parent",
        foreign_keys="Episode.parent_id",
        lazy="joined",
        cascade="all, delete-orphan",
        order_by="Episode.number",
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
        """
        Determine Season state based on episode states.

        Seasons aggregate episode states: Requested → Indexed → Scraped → Ongoing/Completed/Failed
        Uses Partially* states to indicate partial completion across episodes.
        """
        if len(self.episodes) == 0:
            return States.Unreleased

        # Explicit states override everything
        if self.last_state == States.Paused:
            return States.Paused
        if self.last_state == States.Failed:
            return States.Failed

        # Any episode has unreleased/ongoing status
        if any(episode.state in [States.Ongoing, States.Unreleased] for episode in self.episodes):
            return States.Ongoing

        # All episodes completed
        if all(episode.state == States.Completed for episode in self.episodes):
            return States.Completed

        # Some episodes completed
        if any(episode.state in [States.Completed, States.PartiallyCompleted] for episode in self.episodes):
            return States.PartiallyCompleted

        if any(episode.state in [States.Available, States.PartiallyAvailable] for episode in self.episodes):
            return States.PartiallyAvailable

        if any(episode.state in [States.Downloaded, States.PartiallyDownloaded] for episode in self.episodes):
            return States.PartiallyDownloaded

        # Season has been scraped
        if self.is_scraped():
            return States.Scraped

        # Season has been indexed
        if any(episode.state == States.Indexed for episode in self.episodes):
            return States.Indexed

        # All episodes unreleased
        if all(episode.state == States.Unreleased for episode in self.episodes):
            return States.Unreleased

        # Season was requested
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
    id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True)
    parent_id: Mapped[int] = mapped_column(sqlalchemy.ForeignKey("Season.id", ondelete="CASCADE"), use_existing_column=True)
    parent: Mapped["Season"] = relationship(
        back_populates="episodes",
        foreign_keys="Episode.parent_id",
        lazy="joined",
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
    """
    Create a copy of a MediaItem-derived object, preserving its concrete subclass and hierarchy.
    
    Parameters:
        item (MediaItem): The media item (Movie, Show, Season, Episode, or MediaItem) to copy.
    
    Returns:
        MediaItem: A new instance of the same concrete subclass containing copied data from `item`.
    
    Raises:
        ValueError: If `item` is not an instance of a supported MediaItem subclass.
    """
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


# ============================================================================
# SQLAlchemy Event Listeners for Automatic Cleanup
# ============================================================================

# No event listeners needed for FilesystemEntry cleanup!
# The cascade="all, delete-orphan" on MediaItem.filesystem_entries handles everything:
# - When MediaItem is deleted, all FilesystemEntries are automatically deleted (CASCADE)
# - When filesystem_entries.clear() is called, orphaned entries are automatically deleted (delete-orphan)
# - The FilesystemEntry's before_delete event listener still handles VFS cache invalidation