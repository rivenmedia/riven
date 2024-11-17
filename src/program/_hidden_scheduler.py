from datetime import datetime, timedelta
import sched
import threading
import time

from program.media.item import MediaItem


class _HiddenScheduler:
    def __init__(self, program):
        self.program = program
        scheduler = sched.scheduler(time.time, time.sleep)
        #next_time = datetime.now() + timedelta(minutes=1)  # For testing
        next_time = self._get_next_april_first()  # For production
        scheduler.enterabs(next_time.timestamp(), 1, self._add_items)
        scheduler_thread = threading.Thread(target=scheduler.run, daemon=True)
        scheduler_thread.start()

    def _get_next_april_first(self):
        """Get next April 1st at midnight."""
        today = datetime.now()
        current_year = today.year
        april_first = datetime(current_year, 4, 1, 0, 0, 0)
        if today > april_first:
            april_first = datetime(current_year + 1, 4, 1, 0, 0, 0)
        return april_first

    def _add_items(self):
        """Add special items to queue."""
        item = MediaItem(
            {"imdb_id": "tt0090655", "requested_by": "system", "requested_at": datetime.now()}
        )
        self.program.em.add_item(item)