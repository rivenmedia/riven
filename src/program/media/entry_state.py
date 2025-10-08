from enum import Enum


class EntryState(Enum):
    """
    MediaEntry states for tracking download/processing lifecycle.
    
    This is separate from MediaItem States which track the overall item lifecycle.
    EntryState tracks the lifecycle of a single downloaded version (MediaEntry).
    
    State Flow:
    Pending → Downloading → Downloaded → Available → Completed
                    ↓
                  Failed
    """
    Pending = "Pending"  # Entry created, waiting to be downloaded
    Downloading = "Downloading"  # Download in progress (has active_stream)
    Downloaded = "Downloaded"  # Downloaded but not yet in VFS
    Available = "Available"  # Available in VFS (available_in_vfs = True)
    Completed = "Completed"  # Processed by updater
    Failed = "Failed"  # Download/processing failed

