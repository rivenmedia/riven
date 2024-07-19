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

class OverseerrStatus(Enum):
    Requested = "Requested"
    # `Processing` is a valid status but has no effect in the overseerr server AFAIK
    # so we use `Pending` instead
    Pending = "Pending"
    Available = "Available"
    PartiallyAvailable = "PartiallyAvailable"
