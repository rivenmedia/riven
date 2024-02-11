from utils.logger import logger
from program.media.item import MediaItem
from program.media.container import MediaItemContainer
from program.updaters.trakt import Updater as Trakt


class ContentServiceBase:
    """Base class for content providers"""

    def __init__(self, media_items: MediaItemContainer):
        self.media_items = media_items
        self.updater = Trakt()
        self.not_found_ids = []
        self.next_run_time = 0

    def validate(self):
        """Validate the content provider settings."""
        raise NotImplementedError(
            "The 'validate' method must be implemented by subclasses."
        )

    def run(self):
        """Fetch new media from the content provider."""
        raise NotImplementedError("The 'run' method must be implemented by subclasses.")

    def process_items(
        self, items: MediaItemContainer, requested_by: str
    ) -> MediaItemContainer:
        """Process fetched media items and log the results."""
        new_items = [item for item in items if self.is_valid_item(item) and item is not None]
        if not new_items:
            return
        container = self.updater.create_items(new_items)
        added_items = self.media_items.extend(container)
        for item in added_items:
            try:
                item.set("requested_by", requested_by)
            except AttributeError:
                logger.debug("Missing set method for %s, removing..", item.log_string)
                # Implement blacklist or something here.
                # for not just delete.. since we werent able to create an item for it.
                added_items.remove(item)
                self.media_items.remove(item)
                self.media_items.save()
        return added_items

    def is_valid_item(self, item: MediaItem) -> bool:
        """Check if an imdb_id is valid for processing and not already in media_items"""
        is_unique = not any(
            existing_item.imdb_id == item for existing_item in self.media_items.items
        )
        return item is not None and is_unique
