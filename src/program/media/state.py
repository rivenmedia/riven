"""
MediaItem state machine states.

This module defines the states that MediaItems (movies, shows, seasons, episodes)
can be in during their lifecycle through the Riven processing pipeline.
"""
from enum import Enum


class States(Enum):
    """
    MediaItem states for the Riven state machine.

    State Flow Architecture:

    Shows/Seasons:
        Requested → Indexed → Scraped → Ongoing/Completed/Failed
        (Shows/Seasons only go through scraping, then episodes are enqueued)

    Movies/Episodes:
        Requested → Indexed → Scraped → Downloaded → Available → Completed/Failed
        (Movies/Episodes go through full download pipeline)

    State Descriptions:
        Unknown: Default/initial state
        Unreleased: Item has metadata but hasn't aired yet
        Ongoing: Show is currently airing, needs periodic re-scraping
        Requested: Item requested from content service (Overseerr, etc.)
        Indexed: Metadata fetched from indexer (TMDB, TVDB)
        Scraped: Torrent streams found by scrapers
        Downloaded: File downloaded from debrid service
        PartiallyDownloaded: Some episodes downloaded (for seasons)
        Available: File available in VFS (RivenVFS)
        PartiallyAvailable: Some episodes available (for seasons)
        Completed: Processed by media server (Plex, etc.)
        PartiallyCompleted: Some episodes completed (for seasons)
        Failed: Processing failed, requires manual intervention
        Paused: Processing paused by user
    """
    Unknown = "Unknown"
    Unreleased = "Unreleased"
    Ongoing = "Ongoing"
    Requested = "Requested"
    Indexed = "Indexed"
    Scraped = "Scraped"
    Downloaded = "Downloaded"
    PartiallyDownloaded = "Partially downloaded"
    Available = "Available"
    PartiallyAvailable = "Partially available"
    Completed = "Completed"
    PartiallyCompleted = "Partially completed"
    Failed = "Failed"
    Paused = "Paused"
