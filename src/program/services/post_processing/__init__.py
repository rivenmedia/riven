import time
from datetime import datetime

from loguru import logger

from program.db.db import db
from program.db.stream_operations import clear_streams
from program.media.item import MediaItem
from program.media.state import States
from program.services.post_processing.subliminal import Subliminal
from program.settings.manager import settings_manager
from program.utils.notifications import notify_on_complete


class PostProcessing:
    def __init__(self):
        self.key = "post_processing"
        self.initialized = False
        self.settings = settings_manager.settings.post_processing
        self.services = {
            Subliminal: Subliminal()
        }
        self.initialized = True

    def run(self, item: MediaItem):
        if not any(service.service for service in self.services.values()):
            # Check if no post processing service is available (worker sanity check)
            logger.error(f"No post processing service is available. Cannot process {item.log_string} ({item.id})")
            while not any(service.service for service in self.services.values()):
                time.sleep(1)
                yield item
        if Subliminal.should_submit(item):
            self.services[Subliminal].run(item)
        if item.last_state == States.Completed:
            clear_streams(item)
        yield item


def notify(item: MediaItem):
    show = None
    if item.type in ["show", "movie"]:
        _notify(item)
    elif item.type == "episode":
        show = item.parent.parent
    elif item.type == "season":
        show = item.parent
    if show:
        with db.Session() as session:
            show = session.merge(show)
            show.store_state()
            if show.last_state == States.Completed:
                _notify(show)
            session.commit()

def _notify(item: MediaItem):
    duration = round((datetime.now() - item.requested_at).total_seconds())
    logger.success(f"{item.log_string} has been completed in {duration} seconds.")
    if settings_manager.settings.notifications.enabled:
        notify_on_complete(item)
