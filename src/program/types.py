"""Type definitions for Riven.

This module contains pure type declarations with no runtime dependencies
on other program modules to avoid circular imports.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

from RTN import ParsedData
from RTN.file_parser import MediaMetadata
from sqlalchemy.types import TypeDecorator, JSON

if TYPE_CHECKING:
    from program.media.item import MediaItem
    from program.media.media_entry import MediaEntry

# Type aliases using Any to avoid import dependencies at runtime
# These are checked properly at type-check time via TYPE_CHECKING imports elsewhere
Service = Any  # Union of all service types (Content, Scraper, Downloader, FilesystemService, Updater)


class ParsedDataType(TypeDecorator):
    """Custom SQLAlchemy type that stores RTN ParsedData as JSON."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert ParsedData to dict for storage."""
        if value is None:
            return None
        if isinstance(value, ParsedData):
            return value.model_dump()
        if isinstance(value, str):
            # Handle JSON string (from model_dump_json())
            import json
            return json.loads(value)
        return value

    def process_result_value(self, value, dialect):
        """Convert dict back to ParsedData when loading."""
        if value is None:
            return None
        if isinstance(value, dict):
            return ParsedData(**value)
        return value

class MediaMetadataType(TypeDecorator):
    """Custom SQLAlchemy type that stores RTN MediaMetadata (ffprobe data) as JSON."""

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Convert MediaMetadata to dict for storage."""
        if value is None:
            return None
        if isinstance(value, MediaMetadata):
            return value.model_dump()
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            # Handle JSON string
            import json
            return json.loads(value)
        return value

    def process_result_value(self, value, dialect):
        """Convert dict back to MediaMetadata when loading."""
        if value is None:
            return None
        if isinstance(value, dict):
            return MediaMetadata(**value)
        return value

class ProcessedEvent:
    """
    Result of processing an event in the state machine.

    Represents the outcome of a state transition, including the next service
    to process and the items/entries to submit to that service.

    Attributes:
        service: Next service to process (or None if no further processing).
        related_media_items: List of MediaItem or MediaEntry objects to submit.
    """
    service: Optional[Service]
    related_media_items: list["MediaItem"]

@dataclass
class Event:
    """
    Event representing work to be processed by the state machine.

    Can represent either a MediaItem event or a MediaEntry event:
    - MediaItem events: Use item_id or content_item
    - MediaEntry events: Use entry_id or content_entry

    Only one of (item_id, content_item, entry_id, content_entry) should be set.
    """
    emitted_by: Service  # Any service type
    item_id: Optional[str] = None
    content_item: Optional["MediaItem"] = None
    entry_id: Optional[int] = None  # MediaEntry ID for profile-aware processing
    content_entry: Optional["MediaEntry"] = None  # MediaEntry object for new entries
    run_at: datetime = datetime.now()
    item_state: Optional[str] = None  # Cached state for priority sorting (MediaItem or MediaEntry)

    @property
    def is_entry_event(self) -> bool:
        """
        Check if this event is for a MediaEntry (vs MediaItem).

        Returns:
            bool: True if this is a MediaEntry event, False if MediaItem event.
        """
        return self.entry_id is not None or self.content_entry is not None

    @property
    def log_message(self):
        """
        Generate a human-readable log message for this event.

        Returns:
            str: Log message describing the event.
        """
        # MediaEntry events
        if self.entry_id:
            return f"Entry ID {self.entry_id}"
        elif self.content_entry:
            return f"Entry for {self.content_entry.log_string}"

        # MediaItem events
        # Defensive: content_item may be None
        external_id = None
        if self.content_item:
            if self.content_item.imdb_id:
                external_id = f"IMDB ID {self.content_item.imdb_id}"
            elif self.content_item.tmdb_id:
                external_id = f"TMDB ID {self.content_item.tmdb_id}"
            elif self.content_item.tvdb_id:
                external_id = f"TVDB ID {self.content_item.tvdb_id}"
        if self.item_id:
            return f"Item ID {self.item_id}"
        elif external_id:
            return f"External ID {external_id}"
        else:
            return "Unknown Event"