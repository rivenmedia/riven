from enum import Enum


class States(Enum):
    Unknown = "Unknown"
    Requested = "Requested"
    Indexed = "Indexed"
    Scraped = "Scraped"
    Downloaded = "Downloaded"
    Symlinked = "Symlinked"
    Completed = "Completed"
    PartiallyCompleted = "PartiallyCompleted"
    Failed = "Failed"
