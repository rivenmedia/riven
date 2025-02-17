"""MediaItem class"""
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Self

import sqlalchemy
from loguru import logger
from RTN import parse
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from program.db.db import db
from program.managers.sse_manager import sse_manager
from program.media.state import States
from program.media.subtitle import Subtitle

from ..db.db_functions import blacklist_stream, reset_streams
from .stream import Stream


class MediaItem(db.Model):
    """MediaItem class"""
    __tablename__ = "MediaItem"
    id: Mapped[str] = mapped_column(sqlalchemy.String, primary_key=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tvdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    tmdb_id: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
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
    symlinked: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    symlinked_at: Mapped[Optional[datetime]] = mapped_column(sqlalchemy.DateTime, nullable=True)
    symlinked_times: Mapped[Optional[int]] = mapped_column(sqlalchemy.Integer, default=0)
    symlink_path: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    file: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    alternative_folder: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)
    aliases: Mapped[Optional[dict]] = mapped_column(sqlalchemy.JSON, default={})
    is_anime: Mapped[Optional[bool]] = mapped_column(sqlalchemy.Boolean, default=False)
    title: Mapped[Optional[str]] = mapped_column(sqlalchemy.String, nullable=True)

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
        self.tvdb_id = item.get("tvdb_id")
        self.tmdb_id = item.get("tmdb_id")
        self.network = item.get("network")
        self.country = item.get("country")
        self.language = item.get("language")
        self.aired_at = item.get("aired_at")
        self.year = item.get("year")
        self.genres = item.get("genres", [])
        self.aliases = item.get("aliases", {})

        # Plex related
        self.key = item.get("key")
        self.guid = item.get("guid")
        self.update_folder = item.get("update_folder")

        # Overseerr related
        self.overseerr_id = item.get("overseerr_id")

        # Post-processing
        self.subtitles = item.get("subtitles", [])

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
            sse_manager.publish_event("item_update", {"last_state": previous_state, "new_state": new_state, "item_id": self.id})
        self.last_state = new_state
        return (previous_state, new_state)

    def is_stream_blacklisted(self, stream: Stream):
        """Check if a stream is blacklisted for this item."""
        session = object_session(self)
        if session:
            session.refresh(self, attribute_names=["blacklisted_streams"])
        return stream in self.blacklisted_streams

    def blacklist_active_stream(self):
        stream = next((stream for stream in self.streams if stream.infohash == self.active_stream.get("infohash", None)), None)
        if stream:
            self.blacklist_stream(stream)
        else:
            logger.debug(f"No active stream for {self.log_string}, will not blacklist")

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
        """
        Determines the current processing state of the media item based on its attributes and prior state.
        
        This private method evaluates several conditions in a predefined order to establish the media item's state:
        - Returns States.Paused if the last recorded state is Paused.
        - Returns States.Failed if the last recorded state is Failed.
        - Returns States.Completed if the media item has a key or if its update_folder attribute equals "updated".
        - Returns States.Symlinked if the media item is marked as symlinked.
        - Returns States.Downloaded if both file and folder attributes are present.
        - Returns States.Scraped if the media item has been scraped (as determined by the is_scraped() method).
        - Returns States.Indexed if the media item has a title and is released.
        - Returns States.Unreleased if only a title is present.
        - Returns States.Requested if an IMDb ID is provided and the item was requested.
        - Returns States.Unknown if none of the above conditions are met.
        
        Returns:
            States: The derived state of the media item.
        """
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
        """
        Copies media-related attributes from another media item to this instance.
        
        This method updates the current instance with a set of predefined attributes from the
        provided `other` media item. It attempts to retrieve each attribute from `other` and assigns a
        default value if the attribute is not present:
          - title: defaults to None
          - tvdb_id: defaults to None
          - tmdb_id: defaults to None
          - network: defaults to None
          - country: defaults to None
          - language: defaults to None
          - aired_at: defaults to None
          - genres: defaults to an empty list
          - is_anime: defaults to False
          - overseerr_id: defaults to None
        
        Parameters:
            other (object): A media item instance from which to copy attributes. It should ideally have
                            the attributes corresponding to media details, though missing attributes will
                            adopt their default values.
        
        Returns:
            None
        """
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
        """
        Check if the media item has been scraped successfully.
        
        This method determines if the item has been scraped by verifying that it has one or more associated streams and that at least one of these streams is not in the blacklisted set.
        It first retrieves the active session and refreshes the "blacklisted_streams" attribute to ensure up-to-date data. If the item has streams and at least one of them is not blacklisted, it returns True.
        Any errors during the session refresh are caught, logged, and result in the method returning False.
        
        Returns:
            bool: True if the item has valid (non-blacklisted) streams, otherwise False.
        """
        session = object_session(self)
        if session and session.is_active:
            try:
                session.refresh(self, attribute_names=["blacklisted_streams"])
                return (len(self.streams) > 0 and any(stream not in self.blacklisted_streams for stream in self.streams))
            except Exception as e:
                logger.exception(f"Error in is_scraped() for {self.log_string}: {str(e)}")
        return False

    def to_dict(self):
        """
        Convert the media item to a dictionary representation for API responses.
        
        This method serializes the MediaItem instance into a dictionary with key metadata, ensuring that all
        attributes are appropriately formatted. Conditional attributes (like IMDb, TVDB, TMDB IDs, genres, and
        IMDb link) are included only if they exist on the instance. Timestamps and dates are converted to strings
        to ensure a consistent output format.
        
        Returns:
            dict: A dictionary containing:
                - "id" (str): String representation of the unique identifier.
                - "title" (str): The title of the media item.
                - "type" (str): The class name of the media item.
                - "imdb_id" (str or None): IMDb identifier if available.
                - "tvdb_id" (str or None): TVDB identifier if available.
                - "tmdb_id" (str or None): TMDB identifier if available.
                - "state" (str): Name of the current state.
                - "imdb_link" (str or None): Link to the IMDb page if available.
                - "aired_at" (str): Air date of the media item.
                - "genres" (list or None): Genres associated with the media item if available.
                - "is_anime" (bool): True if the media item is classified as anime, otherwise False.
                - "guid" (str): Globally unique identifier.
                - "requested_at" (str): Timestamp when the media item was requested.
                - "requested_by" (str): Identifier for the requester.
                - "scraped_at" (str): Timestamp when the media item was scraped.
                - "scraped_times" (int): Number of times scraping has been attempted.
        """
        return {
            "id": str(self.id),
            "title": self.title,
            "type": self.__class__.__name__,
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
        """
        Reset the media item's attributes to prepare for a re-scraping process.
        
        This method performs the following actions:
        - If a symlink path is set and exists, it removes the symlink and clears the associated attribute.
        - Attempts to remove all associated subtitle files. Any exceptions during subtitle removal are caught and logged as warnings.
        - Clears file-related attributes: 'file', 'folder', and 'alternative_folder'.
        - Resets stream data by calling the 'reset_streams' function and clearing the 'active_stream' attribute.
        - Resets additional flags and timestamps including 'symlinked', 'symlinked_at', 'update_folder', 'scraped_at', 'symlinked_times', 'scraped_times', and 'failed_attempts'.
        - Logs a debug message indicating that the item has been reset.
        
        Returns:
            None
        """
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

    @property
    def log_string(self):
        return self.title or self.id

    @property
    def collection(self):
        """
        Retrieve the collection identifier for the media item.
        
        If the item has a parent, this method returns the parent's collection identifier; otherwise, it returns the item's own id.
        
        Returns:
            The collection identifier, which is either the parent's collection attribute or the item's id.
        """
        return self.parent.collection if self.parent else self.id

    def is_parent_blocked(self) -> bool:
        """
        Determine if this media item or any of its parent items is currently paused.
        
        This method checks if the current item's last state is set to paused, which blocks processing
        for the item and its descendants. If the current item is not paused, the method attempts to
        refresh and retrieve its parent from the associated SQLAlchemy session. If a parent exists,
        the method recursively checks whether any ancestor is paused.
        
        Returns:
            bool: True if this item or any of its parent items is paused, otherwise False.
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
        Recursively retrieves the closest parent media item that is in a Paused state.
        
        This method checks if the current media item is paused. If so, it is considered blocking and returned immediately.
        If the current item is not paused, the method attempts to refresh and access its parent from the active SQLAlchemy session,
        then recursively calls get_blocking_parent on the parent to determine if an ancestor is blocking. If no paused parent is found,
        the method returns None.
        
        Returns:
            Optional[MediaItem]: The nearest parent media item with a Paused state, or None if no such parent exists.
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
        """
        Determine the overall state of the media item based on the states of its associated seasons.
        
        This private method evaluates the state of each season in the `seasons` list and returns
        an aggregated state for the media item according to the following rules (evaluated in order):
        
            - If all seasons are marked as `States.Completed`, return `States.Completed`.
            - If any season is marked as `States.Ongoing` or `States.Unreleased`, return `States.Ongoing`.
            - If any season is marked as either `States.Completed` or `States.PartiallyCompleted`, return `States.PartiallyCompleted`.
            - If all seasons are marked as `States.Symlinked`, return `States.Symlinked`.
            - If all seasons are marked as `States.Downloaded`, return `States.Downloaded`.
            - If the media item is scraped (as determined by the `is_scraped()` method), return `States.Scraped`.
            - If any season is marked as `States.Indexed`, return `States.Indexed`.
            - If all seasons are not released (i.e., `season.is_released` is False), return `States.Unreleased`.
            - If any season is marked as `States.Requested`, return `States.Requested`.
            - If none of these conditions are met, return `States.Unknown`.
        
        Returns:
            A member of the `States` enumeration representing the overall state of the media item.
        """
        if all(season.state == States.Completed for season in self.seasons):
            return States.Completed
        if any(season.state in [States.Ongoing, States.Unreleased] for season in self.seasons):
            return States.Ongoing
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
        if all(not season.is_released for season in self.seasons):
            return States.Unreleased
        if any(season.state == States.Requested for season in self.seasons):
            return States.Requested
        return States.Unknown

    def store_state(self, given_state: States =None) -> None:
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


class Season(MediaItem):
    """Season class"""
    __tablename__ = "Season"
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id"), primary_key=True)
    parent_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("Show.id"), use_existing_column=True)
    parent: Mapped["Show"] = relationship(lazy=False, back_populates="seasons", foreign_keys="Season.parent_id")
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
        """
        Determines and returns the overall state of the media item based on the states of its episodes.
        
        The state is evaluated in the following order:
        1. If there is at least one episode and **all** episodes are in the Completed state, returns Completed.
        2. If there is at least one episode in the Unreleased state but not all episodes are Unreleased, returns Ongoing.
        3. If any episode is in the Completed state (when not all are Completed), returns PartiallyCompleted.
        4. If **all** episodes are in the Symlinked state, returns Symlinked.
        5. If **all** episodes have both file and folder attributes set, returns Downloaded.
        6. If the media item has been scraped (as determined by `is_scraped()`), returns Scraped.
        7. If any episode is in the Indexed state, returns Indexed.
        8. If any episode is in the Unreleased state (and the previous Unreleased check did not apply), returns Unreleased.
        9. If any episode is in the Requested state, returns Requested.
        10. If none of the above conditions are met, returns Unknown.
        
        If there are no episodes, the method returns Unreleased.
        
        Returns:
            States: The overall state determined from the episodes.
        """
        if len(self.episodes) > 0:
            if all(episode.state == States.Completed for episode in self.episodes):
                return States.Completed
            if any(episode.state == States.Unreleased for episode in self.episodes):
                if any(episode.state != States.Unreleased for episode in self.episodes):
                    return States.Ongoing
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
        return self.parent.title


class Episode(MediaItem):
    """Episode class"""
    __tablename__ = "Episode"
    id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("MediaItem.id"), primary_key=True)
    parent_id: Mapped[str] = mapped_column(sqlalchemy.ForeignKey("Season.id"), use_existing_column=True)
    parent: Mapped["Season"] = relationship(back_populates="episodes", foreign_keys="Episode.parent_id", lazy="joined")

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
        return parse(self.file).episodes

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