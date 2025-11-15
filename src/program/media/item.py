"""MediaItem class"""

from datetime import datetime
from typing import Any, Literal, TYPE_CHECKING

import sqlalchemy
from loguru import logger
from PTT import parse_title
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from program.db.db import db
from program.media.state import States
from program.media.subtitle_entry import SubtitleEntry

from .stream import Stream

if TYPE_CHECKING:
    from program.media.filesystem_entry import FilesystemEntry


class MediaItem(db.Model):
    """MediaItem class"""

    __tablename__ = "MediaItem"

    id: Mapped[int] = mapped_column(sqlalchemy.Integer, primary_key=True)
    imdb_id: Mapped[str | None]
    tvdb_id: Mapped[str | None]
    tmdb_id: Mapped[str | None]
    title: Mapped[str | None]
    poster_path: Mapped[str | None]
    number: Mapped[int | None]
    type: Mapped[
        Literal[
            "episode",
            "season",
            "show",
            "movie",
        ]
    ] = mapped_column(nullable=False)
    requested_at: Mapped[datetime | None] = mapped_column(
        sqlalchemy.DateTime, default=datetime.now()
    )
    requested_by: Mapped[str | None]
    requested_id: Mapped[int | None]
    indexed_at: Mapped[datetime | None]
    scraped_at: Mapped[datetime | None]
    scraped_times: Mapped[int | None] = mapped_column(sqlalchemy.Integer, default=0)
    active_stream: Mapped[dict | None] = mapped_column(sqlalchemy.JSON, nullable=True)
    streams: Mapped[list[Stream]] = relationship(
        secondary="StreamRelation",
        back_populates="parents",
        lazy="selectin",
        cascade="all",
    )
    blacklisted_streams: Mapped[list[Stream]] = relationship(
        secondary="StreamBlacklistRelation",
        back_populates="blacklisted_parents",
        lazy="selectin",
        cascade="all",
    )

    aliases: Mapped[dict | None] = mapped_column(sqlalchemy.JSON, default={})
    is_anime: Mapped[bool | None] = mapped_column(sqlalchemy.Boolean, default=False)
    network: Mapped[str | None]
    country: Mapped[str | None]
    language: Mapped[str | None]
    aired_at: Mapped[datetime | None]
    year: Mapped[int | None]
    genres: Mapped[list[str] | None] = mapped_column(sqlalchemy.JSON, nullable=True)

    # Rating metadata (normalized for filtering)

    ## 0.0-10.0 scale (TMDB vote_average)
    rating: Mapped[float | None]

    ## US content rating (G, PG, PG-13, R, NC-17, TV-Y, TV-PG, TV-14, TV-MA, etc.)
    content_rating: Mapped[str | None]

    updated: Mapped[bool | None] = mapped_column(sqlalchemy.Boolean, default=False)
    guid: Mapped[str | None]
    overseerr_id: Mapped[int | None]
    last_state: Mapped[States | None] = mapped_column(
        sqlalchemy.Enum(States), default=States.Unknown
    )
    filesystem_entries: Mapped[list["FilesystemEntry"]] = relationship(
        "FilesystemEntry",
        back_populates="media_item",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    subtitles: Mapped[list[SubtitleEntry]] = relationship(
        SubtitleEntry,
        back_populates="media_item",
        lazy="selectin",
        cascade="all, delete-orphan",
        overlaps="filesystem_entries",
    )
    failed_attempts: Mapped[int | None] = mapped_column(sqlalchemy.Integer, default=0)

    __mapper_args__ = {
        "polymorphic_identity": "mediaitem",
        "polymorphic_on": "type",
    }

    __table_args__ = (
        Index("ix_mediaitem_type", "type"),
        Index("ix_mediaitem_requested_by", "requested_by"),
        Index("ix_mediaitem_title", "title"),
        Index("ix_mediaitem_poster_path", "poster_path"),
        Index("ix_mediaitem_imdb_id", "imdb_id"),
        Index("ix_mediaitem_tvdb_id", "tvdb_id"),
        Index("ix_mediaitem_tmdb_id", "tmdb_id"),
        Index("ix_mediaitem_network", "network"),
        Index("ix_mediaitem_country", "country"),
        Index("ix_mediaitem_language", "language"),
        Index("ix_mediaitem_aired_at", "aired_at"),
        Index("ix_mediaitem_year", "year"),
        Index("ix_mediaitem_rating", "rating"),
        Index("ix_mediaitem_content_rating", "content_rating"),
        Index("ix_mediaitem_overseerr_id", "overseerr_id"),
        Index("ix_mediaitem_type_aired_at", "type", "aired_at"),  # Composite index
    )

    def __init__(self, item: dict | None) -> None:
        if item is None:
            return
        self.requested_at = item.get("requested_at", datetime.now())
        self.requested_by = item.get("requested_by")
        self.requested_id = item.get("requested_id")

        self.indexed_at = None

        self.scraped_at = None
        self.scraped_times = 0
        self.active_stream = item.get("active_stream", {})
        self.streams = []
        self.blacklisted_streams = []

        # Media related
        self.title = item.get("title")
        self.poster_path = item.get("poster_path")
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
        self.rating = item.get("rating")
        self.content_rating = item.get("content_rating")

        # Media server related
        self.updated = item.get("updated", False)
        self.guid = item.get("guid")

        # Overseerr related
        self.overseerr_id = item.get("overseerr_id")

        # Post-processing
        self.subtitles = item.get("subtitles", [])

    def store_state(
        self,
        given_state: States | None = None,
    ) -> tuple[States | None, States]:
        """Store the state of the item and notify about state changes."""

        previous_state = self.last_state
        new_state = given_state or self._determine_state()
        self.last_state = new_state

        # Notify about state change via NotificationService
        if previous_state and previous_state != new_state:
            try:
                from program.program import riven
                from program.services.notifications import NotificationService

                notification_service = riven.all_services.get(NotificationService)
                if notification_service:
                    notification_service.run(
                        self,
                        previous_state=previous_state,
                        new_state=new_state,
                    )
            except Exception as e:
                # Fallback: log error but don't break state storage
                logger.debug(f"Failed to send state change notification: {e}")

        return (previous_state, new_state)

    def blacklist_active_stream(self) -> bool:
        """Blacklist the currently active stream for this item."""

        if not self.active_stream:
            logger.debug(f"No active stream for {self.log_string}, will not blacklist")
            return False

        def find_and_blacklist_stream(streams):
            stream = next(
                (
                    s
                    for s in streams
                    if s.infohash == self.active_stream.get("infohash")
                ),
                None,
            )
            if stream:
                self.blacklist_stream(stream)
                logger.debug(
                    f"Blacklisted stream {stream.infohash} for {self.log_string}"
                )
                return True
            return False

        if find_and_blacklist_stream(self.streams):
            return True

        if self.type == "episode":
            if self.parent and find_and_blacklist_stream(self.parent.streams):
                return True
            if (
                self.parent
                and self.parent.parent
                and find_and_blacklist_stream(self.parent.parent.streams)
            ):
                return True

        logger.debug(
            f"Unable to find stream from item hierarchy for {self.log_string}, will not blacklist"
        )
        return False

    def blacklist_stream(self, stream: Stream) -> bool:
        """Blacklist a stream by moving it from streams to blacklisted_streams."""

        if stream in self.streams:
            self.streams.remove(stream)
            if stream not in self.blacklisted_streams:
                self.blacklisted_streams.append(stream)
            logger.debug(f"Blacklisted stream {stream.infohash} for {self.log_string}")
            return True
        return False

    def unblacklist_stream(self, stream: Stream) -> None:
        """Unblacklist a stream by moving it from blacklisted_streams to streams."""

        if stream in self.blacklisted_streams:
            self.blacklisted_streams.remove(stream)

            if stream not in self.streams:
                self.streams.append(stream)

            logger.debug(
                f"Unblacklisted stream {stream.infohash} for {self.log_string}"
            )

    def schedule(
        self,
        run_at: datetime,
        task_type: str = "episode_release",
        *,
        offset_seconds: int | None = None,
        reason: str | None = None,
    ) -> bool:
        """
        Schedule a task for this item at a specific time.

        Creates a ScheduledTask row (idempotent via unique index).
        Opens its own session (session-per-request).
        """

        from sqlalchemy.exc import IntegrityError
        from program.scheduling.models import ScheduledTask, ScheduledStatus
        from program.db.db import db

        if not self.id:
            logger.error("Cannot schedule task for unsaved item (missing id)")
            return False

        if not run_at:
            logger.error("Cannot schedule task without a run_at time")
            return False

        try:
            # Defensive: avoid scheduling in the past
            if run_at <= datetime.now():
                logger.debug(
                    f"Refusing to schedule past/now task for {self.log_string} at {run_at.isoformat()} [{task_type}]"
                )
                return False
        except Exception:
            pass

        payload = {
            "item_id": int(self.id),
            "task_type": task_type,
            "scheduled_for": run_at,
            "status": ScheduledStatus.Pending,
            "offset_seconds": offset_seconds,
            "reason": reason,
        }

        try:
            with db.Session() as session:
                st = ScheduledTask(**payload)
                session.add(st)
                session.commit()
                logger.info(
                    f"Scheduled {task_type} for {self.log_string} at {run_at.isoformat()} (offset={offset_seconds})"
                )
                return True
        except IntegrityError:
            logger.debug(
                f"Schedule already exists for item {self.id} at {run_at.isoformat()} [{task_type}]"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to schedule task for {self.log_string}: {e}")
            return False

        return False

    @property
    def is_released(self) -> bool:
        """Check if an item has been released."""

        if not self.aired_at:
            return False

        return self.aired_at and self.aired_at <= datetime.now()

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

    def is_scraped(self) -> bool:
        """Check if the item has been scraped."""

        session = object_session(self)

        if session and session.is_active:
            try:
                session.refresh(self, attribute_names=["blacklisted_streams"])
                return len(self.streams) > 0 and any(
                    stream not in self.blacklisted_streams for stream in self.streams
                )
            except:
                pass

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
            "tmdb_id": self.tvdb_id if hasattr(self, "tvdb_id") else None,
        }

        if self.type == "season":
            parent_title = self.parent.title
            season_number = self.number
            parent_ids["trakt_id"] = (
                self.parent.trakt_id
                if hasattr(self, "parent") and hasattr(self.parent, "trakt_id")
                else None
            )
            parent_ids["imdb_id"] = (
                self.parent.imdb_id
                if hasattr(self, "parent") and hasattr(self.parent, "imdb_id")
                else None
            )
            parent_ids["tvdb_id"] = (
                self.parent.tvdb_id
                if hasattr(self, "parent") and hasattr(self.parent, "tvdb_id")
                else None
            )
            parent_ids["tmdb_id"] = (
                self.parent.tmdb_id
                if hasattr(self, "parent") and hasattr(self.parent, "tmdb_id")
                else None
            )
        elif self.type == "episode":
            parent_title = self.parent.parent.title
            season_number = self.parent.number
            episode_number = self.number
            parent_ids["trakt_id"] = (
                self.parent.parent.trakt_id
                if hasattr(self, "parent") and hasattr(self.parent, "trakt_id")
                else None
            )
            parent_ids["imdb_id"] = (
                self.parent.parent.imdb_id
                if hasattr(self, "parent")
                and hasattr(self.parent, "parent")
                and hasattr(self.parent.parent, "imdb_id")
                else None
            )
            parent_ids["tvdb_id"] = (
                self.parent.parent.tvdb_id
                if hasattr(self, "parent")
                and hasattr(self.parent, "parent")
                and hasattr(self.parent.parent, "tvdb_id")
                else None
            )
            parent_ids["tmdb_id"] = (
                self.parent.parent.tmdb_id
                if hasattr(self, "parent")
                and hasattr(self.parent, "parent")
                and hasattr(self.parent.parent, "tmdb_id")
                else None
            )

        data = {
            "id": str(self.id),
            "title": self.title,
            "poster_path": self.poster_path,
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
            "rating": self.rating,
            "content_rating": self.content_rating,
            "requested_at": str(self.requested_at),
            "requested_by": self.requested_by,
            "scraped_at": str(self.scraped_at),
            "scraped_times": self.scraped_times,
        }

        if hasattr(self, "seasons") or hasattr(self, "episodes"):
            data["parent_ids"] = parent_ids

        return data

    def to_extended_dict(
        self, abbreviated_children=False, with_streams=False
    ) -> dict[str, Any]:
        """Convert item to extended dictionary (API response)"""

        dict = self.to_dict()
        match self:
            case Show():
                dict["seasons"] = (
                    [
                        season.to_extended_dict(with_streams=with_streams)
                        for season in self.seasons
                    ]
                    if not abbreviated_children
                    else self.represent_children
                )
            case Season():
                dict["episodes"] = (
                    [
                        episode.to_extended_dict(with_streams=with_streams)
                        for episode in self.episodes
                    ]
                    if not abbreviated_children
                    else self.represent_children
                )
        dict["language"] = self.language if hasattr(self, "language") else None
        dict["country"] = self.country if hasattr(self, "country") else None
        dict["network"] = self.network if hasattr(self, "network") else None
        if with_streams:
            dict["streams"] = [
                stream.to_dict() for stream in getattr(self, "streams", [])
            ]
            dict["blacklisted_streams"] = [
                stream.to_dict() for stream in getattr(self, "blacklisted_streams", [])
            ]
            dict["active_stream"] = (
                self.active_stream if hasattr(self, "active_stream") else None
            )
        dict["number"] = self.number if hasattr(self, "number") else None
        dict["is_anime"] = self.is_anime if hasattr(self, "is_anime") else None

        dict["filesystem_entry"] = (
            self.filesystem_entry.to_dict() if self.filesystem_entry else None
        )
        dict["media_metadata"] = (
            self.filesystem_entry.media_metadata if self.filesystem_entry else None
        )
        dict["subtitles"] = (
            [subtitle.to_dict() for subtitle in self.subtitles]
            if hasattr(self, "subtitles")
            else []
        )
        # Include embedded subtitles from media_metadata
        if self.filesystem_entry and self.filesystem_entry.media_metadata:
            embedded_subs = self.filesystem_entry.media_metadata.get(
                "subtitle_tracks", []
            )
            if embedded_subs:
                dict["subtitles"].extend(embedded_subs)
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

    # Filesystem entry properties
    @property
    def filesystem_entry(self) -> "FilesystemEntry | None":
        """
        Return the first filesystem entry for this media item to preserve backward compatibility.

        Returns:
            The first `FilesystemEntry` instance if any exist, otherwise `None`.
        """
        return self.filesystem_entries[0] if self.filesystem_entries else None

    @property
    def filesystem_path(self) -> str | None:
        """
        Return the filesystem path of the first FilesystemEntry for this media item, if any.

        Returns:
            The filesystem path string from the first entry, or None if no entries exist.
        """

        return self.filesystem_entries[0].path if self.filesystem_entries else None

    @property
    def available_in_vfs(self) -> bool:
        """
        Indicates whether any filesystem entry for this media item is available in the mounted VFS.

        Returns:
            `true` if at least one associated filesystem entry is available in the mounted VFS, `false` otherwise.
        """

        return (
            any(fe.available_in_vfs for fe in self.filesystem_entries)
            if self.filesystem_entries
            else False
        )

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

        Clears filesystem entries, subtitles, active and related streams, and resets
        scraping-related metadata (updated, scraped_at, scraped_times, failed_attempts).

        ORM cascade handles deletion of associated records. VFS sync is called to remove
        this item's nodes from the VFS tree (targeted removal, not full rebuild).

        Note: VFS sync is called BEFORE clearing entries so it can still access them
        to generate the paths to remove. The entries aren't committed yet, so they're
        still accessible in the session.
        """

        # Remove VFS nodes BEFORE clearing entries (so we can still access them)
        from program.services.filesystem import FilesystemService
        from program.program import riven

        filesystem_service = riven.services.get(FilesystemService)

        if filesystem_service and filesystem_service.riven_vfs:
            filesystem_service.riven_vfs.remove(self)

        # Clear filesystem entries - ORM automatically deletes orphaned entries
        self.filesystem_entries.clear()

        # Clear subtitles (event listener deletes files from disk on commit)
        self.subtitles.clear()

        # Clear streams using ORM relationship operations (database CASCADE handles orphans)
        self.streams.clear()
        self.active_stream = {}

        # Reset scraping metadata
        self.updated = False
        self.scraped_at = None
        self.scraped_times = 0
        self.failed_attempts = 0

        logger.debug(f"Item {self.log_string} has been reset")

    @property
    def log_string(self) -> str:
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

    def _get_top_parent(self) -> "MediaItem":
        """Return the top-most parent item in the hierarchy."""

        if self.type == "season" and getattr(self, "parent", None):
            return self.parent

        if self.type == "episode" and getattr(
            getattr(self, "parent", None), "parent", None
        ):
            return self.parent.parent

        return self


class Movie(MediaItem):
    """Movie class"""

    __tablename__ = "Movie"

    id: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True
    )

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

    id: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True
    )
    seasons: Mapped[list["Season"]] = relationship(
        back_populates="parent",
        foreign_keys="Season.parent_id",
        lazy="joined",
        cascade="all, delete-orphan",
        order_by="Season.number",
    )
    release_data: Mapped[dict | None] = mapped_column(sqlalchemy.JSON, default={})
    tvdb_status: Mapped[str | None] = mapped_column(sqlalchemy.String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "show",
        "polymorphic_load": "selectin",
    }

    def __init__(self, item: dict):
        self.type = "show"
        self.locations = item.get("locations", [])
        self.seasons = item.get("seasons", [])
        self.release_data = item.get("release_data", {})
        self.tvdb_status = item.get("tvdb_status")

        super().__init__(item)

    def _determine_state(self):
        if all(season.state == States.Paused for season in self.seasons):
            return States.Paused

        if all(season.state == States.Failed for season in self.seasons):
            return States.Failed

        if all(season.state == States.Completed for season in self.seasons):
            # Check TVDB status - only mark as Completed if the show has ended
            # If status is "Continuing" or "Upcoming", the show is still ongoing
            if self.tvdb_status and self.tvdb_status.lower() in [
                "continuing",
                "upcoming",
            ]:
                return States.Ongoing

            return States.Completed

        if any(
            season.state in [States.Ongoing, States.Unreleased]
            for season in self.seasons
        ):
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

    def store_state(self, given_state: States | None = None) -> tuple[States, States]:
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
            self.seasons.append(season)
            season.parent = self
            self.seasons = sorted(self.seasons, key=lambda s: s.number)

    def get_absolute_episode(
        self,
        episode_number: int,
        season_number: int | None = None,
    ) -> "Episode | None":
        """Get the absolute episode number based on season and episode."""
        if not episode_number or episode_number == 0:
            return None

        if season_number is not None:
            season = next((s for s in self.seasons if s.number == season_number), None)
            if season:
                episode = next(
                    (e for e in season.episodes if e.number == episode_number), None
                )
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

    id: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True
    )
    parent_id: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("Show.id", ondelete="CASCADE"), use_existing_column=True
    )
    parent: Mapped["Show"] = relationship(
        lazy=False,
        back_populates="seasons",
        foreign_keys="Season.parent_id",
    )
    episodes: Mapped[list["Episode"]] = relationship(
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

    def __getattribute__(self, name):
        """Override attribute access to inherit from parent show if not set"""

        # List of attributes that should be inherited from parent
        inherited_attrs = {
            "genres",
            "country",
            "network",
            "language",
            "is_anime",
            "rating",
            "content_rating",
            "poster_path",
        }

        # Get the value normally first
        value = object.__getattribute__(self, name)

        # If it's an inherited attribute and the value is empty/None, try to get from parent
        if name in inherited_attrs and not value:
            try:
                parent = object.__getattribute__(self, "parent")
                if parent:
                    return getattr(parent, name, value)
            except AttributeError:
                pass

        return value

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
    id: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("MediaItem.id", ondelete="CASCADE"), primary_key=True
    )
    parent_id: Mapped[int] = mapped_column(
        sqlalchemy.ForeignKey("Season.id", ondelete="CASCADE"), use_existing_column=True
    )
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

    def __repr__(self):
        return f"Episode:{self.number}:{self.state.name}"

    def __hash__(self):
        return super().__hash__()

    def copy(self, other, copy_parent=True):
        super(Episode, self).copy(other)
        if copy_parent and other.parent:
            self.parent = Season(item={}).copy(other.parent)
        return self

    def get_file_episodes(self) -> list[int]:
        if not self.filesystem_entry or not self.filesystem_entry.original_filename:
            raise ValueError("The filesystem entry must have an original filename.")
        # return list of episodes
        return parse_title(self.filesystem_entry.original_filename)["episodes"]

    def __getattribute__(self, name):
        """Override attribute access to inherit from parent show (through season) if not set"""
        # List of attributes that should be inherited from parent show
        inherited_attrs = {
            "genres",
            "country",
            "network",
            "language",
            "is_anime",
            "rating",
            "content_rating",
            "poster_path",
        }

        # Get the value normally first
        value = object.__getattribute__(self, name)

        # If it's an inherited attribute and the value is empty/None, try to get from parent show
        if name in inherited_attrs and not value:
            try:
                parent = object.__getattribute__(self, "parent")
                if parent and hasattr(parent, "parent"):
                    return getattr(parent.parent, name, value)
            except AttributeError:
                pass

        return value

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
