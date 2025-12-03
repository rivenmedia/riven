from collections.abc import AsyncGenerator
from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.services.post_processing.subtitles.subtitle import SubtitleService
from program.settings import settings_manager
from program.core.runner import Runner, RunnerResult
from program.settings.models import PostProcessing as PostProcessingModel


class PostProcessing(Runner[PostProcessingModel]):
    def __init__(self):
        super().__init__()

        self.settings = settings_manager.settings.post_processing

        # Initialize services in order of execution
        # SubtitleService runs second and can use the metadata
        self.services = {
            SubtitleService: SubtitleService(),
        }

        self.initialized = True

    @classmethod
    def get_key(cls) -> str:
        return "post_processing"

    def _get_items_to_process(self, item: MediaItem) -> list[MediaItem]:
        """
        Get list of items to process based on item type.

        Expands shows/seasons into episodes, returns movies/episodes as-is.

        Args:
            item: MediaItem to process

        Returns:
            List of movie/episode items to process
        """

        if isinstance(item, (Movie, Episode)):
            return [item]
        elif isinstance(item, Show):
            return [
                e
                for s in item.seasons
                for e in s.episodes
                if e.last_state == States.Completed
            ]
        elif isinstance(item, Season):
            return [e for e in item.episodes if e.last_state == States.Completed]

        return []

    async def run(self, item: MediaItem) -> AsyncGenerator[RunnerResult[MediaItem]]:
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
            yield RunnerResult(media_items=[item])
            return

        # Handle subtitles
        for process_item in items_to_process:
            if self.services[SubtitleService].should_submit(process_item):
                self.services[SubtitleService].run(process_item)

            # Clean up streams when item is completed -- TODO: BLACKLISTING WONT WORK, WHY?
            # if process_item.last_state == States.Completed:
            #     process_item.streams.clear()

        logger.info(f"Post-processing complete for {item.log_string}")
        yield RunnerResult(media_items=[item])
