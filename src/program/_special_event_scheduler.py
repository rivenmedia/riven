from datetime import datetime, timedelta
import sched
import threading
import time

from program.media.item import MediaItem
from program.utils.logging import logger


from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class SpecialEvent:
    imdb_ids: List[str]
    month: int
    day: int
    requested_by: str = "system"
    debug_minutes: Optional[int] = None  # For testing purposes
    log_event: bool = True

class _SpecialEventScheduler:
    def __init__(self, program):
        self.program = program
        self.events: Dict[str, SpecialEvent] = {
            "april_fools": SpecialEvent(
                imdb_ids=["tt0090655"], # April Fool's Day
                month=4,
                day=1,
                #debug_minutes=1,  # Remove this in production
                log_event=False,
            ),
            "christmas": SpecialEvent(
                imdb_ids=[
                    "tt0099785",  # Home Alone
                ],
                month=12,
                day=25,
            ),
        }
        
        self._setup_schedulers()

    def _setup_schedulers(self):
        """Setup schedulers for all special events."""
        for event_name, event in self.events.items():
            scheduler = sched.scheduler(time.time, time.sleep)
            next_time = (
                datetime.now() + timedelta(minutes=event.debug_minutes)
                if event.debug_minutes is not None
                else self._get_next_date(event.month, event.day)
            )
            scheduler.enterabs(
                next_time.timestamp(), 
                1, 
                self._add_items, 
                argument=(event,)
            )
            scheduler_thread = threading.Thread(
                target=scheduler.run,
                name=f"SpecialEvent_{event_name}",
                daemon=True
            )
            scheduler_thread.start()
            if event.log_event:
                logger.debug(f"Scheduled special event \"{event_name}\" for {next_time}")

    def _get_next_date(self, month: int, day: int) -> datetime:
        """Get next occurrence of a specific month and day at midnight."""
        today = datetime.now()
        current_year = today.year
        event_date = datetime(current_year, month, day, 0, 0, 0)
        
        if today > event_date:
            event_date = datetime(current_year + 1, month, day, 0, 0, 0)
            
        return event_date

    def _add_items(self, event: SpecialEvent):
        """Add special items to queue."""
        if event.log_event:
            logger.debug("Adding system items for special event")
        for imdb_id in event.imdb_ids:
            item = MediaItem({
                "imdb_id": imdb_id,
                "requested_by": event.requested_by,
                "requested_at": datetime.now()
            })
            self.program.em.add_item(item)