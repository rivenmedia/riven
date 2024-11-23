from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from program.media.item import MediaItem

@dataclass
class Event:
    emitted_by: 'Service'  # Forward reference to avoid import
    item_id: Optional[str] = None
    content_item: Optional[MediaItem] = None
    run_at: datetime = datetime.now()

    @property
    def log_message(self):
        if self.content_item:
            return f"Event for {self.content_item.log_string}"
        return f"Event for Item ID: {self.item_id}"