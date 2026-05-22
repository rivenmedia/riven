from loguru import logger

from program.media.item import Episode, MediaItem, Movie, Season, Show
from program.media.state import States
from program.services.post_processing.subtitles.subtitle import SubtitleService
from program.settings import settings_manager
from program.core.runner import MediaItemGenerator, Runner, RunnerResult
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

    def run(self, item: MediaItem) -> MediaItemGenerator:
        """
        Run post-processing services on an item.

        Services are executed in order:
        1. SubtitleService - Fetches subtitles using analysis metadata

        Args:
            item: MediaItem to process (can be show, season, movie, or episode)
        """
        from program.managers.pipeline_activity import (
            report_pipeline_activity_for_item,
        )

        item_id = getattr(item, "id", None)
        try:
            report_pipeline_activity_for_item(item, "Post-processing")
            items_to_process = self._get_items_to_process(item)

            if not items_to_process:
                logger.debug(f"No items to process for {item.log_string}")
                yield RunnerResult(media_items=[item])
                return

            for process_item in items_to_process:
                if self.services[SubtitleService].should_submit(process_item):
                    report_pipeline_activity_for_item(
                        item, "Fetching subtitles"
                    )
                    self.services[SubtitleService].run(process_item)

            logger.info(f"Post-processing complete for {item.log_string}")
            yield RunnerResult(media_items=[item])
        finally:
            if item_id is not None:
                try:
                    from kink import di

                    from program.program import Program

                    di[Program].em.clear_pipeline_activity(int(item_id))
                except Exception:
                    pass
