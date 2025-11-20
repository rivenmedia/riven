from loguru import logger

from program.media.item import MediaItem
from program.media.state import States
from program.services.post_processing.subtitles.subtitle import SubtitleService
from program.settings.manager import settings_manager


class PostProcessing:
    def __init__(self):
        self.key = "post_processing"
        self.initialized = False
        self.settings = settings_manager.settings.post_processing

        # Initialize services in order of execution
        # SubtitleService runs second and can use the metadata
        self.services = {
            SubtitleService: SubtitleService(),
        }
        self.initialized = True

    def _get_items_to_process(self, item: MediaItem) -> list[MediaItem]:
        """
        Get list of items to process based on item type.

        Expands shows/seasons into episodes, returns movies/episodes as-is.

        Args:
            item: MediaItem to process

        Returns:
            List of movie/episode items to process
        """
        if item.type in ["movie", "episode"]:
            return [item]
        elif item.type == "show":
            return [
                e
                for s in item.seasons
                for e in s.episodes
                if e.last_state == States.Completed
            ]
        elif item.type == "season":
            return [e for e in item.episodes if e.last_state == States.Completed]
        return []

    def run(self, item: MediaItem):
        """
        Run post-processing services on an item.

        Services are executed in order:
        1. SubtitleService - Fetches subtitles using analysis metadata

        Args:
            item: MediaItem to process (can be show, season, movie, or episode)
        """
        # Get items to process (expand shows/seasons to episodes)
        items_to_process = self._get_items_to_process(item)

        if not items_to_process:
            logger.debug(f"No items to process for {item.log_string}")
            yield item
            return

        # handle subtitles
        for process_item in items_to_process:
            if self.services[SubtitleService].should_submit(process_item):
                self.services[SubtitleService].run(process_item)

            # Clean up streams when item is completed -- TODO: BLACKLISTING WONT WORK, WHY?
            # if process_item.last_state == States.Completed:
            #     process_item.streams.clear()

        logger.info(f"Post-processing complete for {item.log_string}")
        yield item
