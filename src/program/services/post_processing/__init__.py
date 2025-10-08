"""
Post-Processing service for Riven.

This module orchestrates post-processing services that run after download:
1. MediaAnalysisService - Analyzes media files with ffprobe
2. SubtitleService - Fetches subtitles from providers

Services are executed in order, with later services able to use metadata
from earlier services (e.g., SubtitleService uses ffprobe data from MediaAnalysisService).

Processes MediaEntry objects (not MediaItem) since each profile can have
different files requiring different post-processing.
"""
from loguru import logger

from program.media.media_entry import MediaEntry
from program.services.post_processing.media_analysis import MediaAnalysisService
from program.services.post_processing.subtitles.subtitle import SubtitleService
from program.settings.manager import settings_manager


class PostProcessing:
    """
    Post-processing orchestrator service.

    Coordinates multiple post-processing services in sequence:
    1. MediaAnalysisService - FFprobe analysis (always runs)
    2. SubtitleService - Subtitle fetching (optional)

    Each service can use metadata from previous services.

    Attributes:
        key: Service identifier ("post_processing").
        initialized: Always True (service always available).
        settings: Post-processing settings from settings_manager.
        services: Dict of post-processing service instances.
    """
    def __init__(self):
        """
        Initialize the PostProcessing service.

        Creates service instances in execution order:
        1. MediaAnalysisService (always enabled)
        2. SubtitleService (optional, based on settings)
        """
        self.key = "post_processing"
        self.initialized = False
        self.settings = settings_manager.settings.post_processing

        # Initialize services in order of execution
        # MediaAnalysisService runs first to populate metadata
        # SubtitleService runs second and can use the metadata
        self.services = {
            MediaAnalysisService: MediaAnalysisService(),
            SubtitleService: SubtitleService()
        }
        self.initialized = True

    def run(self, entry: MediaEntry):
        """
        Run post-processing services on a MediaEntry.

        Services are executed in order:
        1. MediaAnalysisService - Analyzes media file (ffprobe)
        2. SubtitleService - Fetches subtitles using analysis metadata

        Args:
            entry: MediaEntry to process (represents a single downloaded file)
        """
        # Run media analysis first
        self.services[MediaAnalysisService].run(entry)

        # Run subtitle service second (uses metadata from analysis)
        if self.services[SubtitleService].initialized:
                self.services[SubtitleService].run(entry)

        logger.info(f"Post-processing complete for {entry.log_string}")

        yield entry
