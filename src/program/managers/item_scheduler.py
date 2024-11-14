from datetime import datetime, timedelta
from sqlalchemy import select

from program.db import db
from program.media.item import MediaItem
from program.media.state import States
from program.types import Event
from program.utils.logging import logger


class ItemScheduler:
    """Service to schedule items based on their air dates"""
    
    def __init__(self):
        self.initialized = True
        self.processing_delay = timedelta(hours=4)  # Delay after air date

    def schedule_item(self, item_id: str, aired_at: datetime, event_manager) -> None:
        """Schedule an individual item if it's upcoming"""
        if not aired_at or aired_at <= datetime.now():
            return

        processing_time = aired_at + self.processing_delay
        event = Event(emitted_by=ItemScheduler, item_id=item_id)
        event_manager.schedule_event(event, run_at=processing_time)
        logger.debug(f"Scheduled item {item_id} for processing at {processing_time}")

    def schedule_upcoming_items(self, event_manager) -> None:
        """Schedule all upcoming items from the database"""
        with db.Session() as session:
            upcoming_items = session.execute(
                select(MediaItem.id, MediaItem.aired_at)
                .where(MediaItem.type.in_(["movie", "episode"]))
                .where(MediaItem.aired_at > (datetime.now() + self.processing_delay))
                .where(MediaItem.last_state == States.Unreleased)
            ).scalars().all()

            for item_id, aired_at in upcoming_items:
                self.schedule_item(item_id, aired_at, event_manager)

        logger.debug(f"Scheduled {len(upcoming_items)} upcoming items")
