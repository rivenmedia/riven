from enum import Enum


class States(Enum):
    Unknown = "Unknown"
    Unreleased = "Unreleased"
    Ongoing = "Ongoing"
    Requested = "Requested"
    Indexed = "Indexed"
    Scraped = "Scraped"
    Downloaded = "Downloaded"
    Symlinked = "Symlinked"
    Completed = "Completed"
    PartiallyCompleted = "PartiallyCompleted"
    Failed = "Failed"
    Paused = "Paused"
