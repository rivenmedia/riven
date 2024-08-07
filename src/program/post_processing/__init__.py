from program.media.item import MediaItem
from program.post_processing.subliminal import Subliminal
from program.settings.manager import settings_manager


class PostProcessing:
    def __init__(self):
        self.key = "post_processing"
        self.initialized = False
        self.settings = settings_manager.settings.post_processing
        self.services = {
            Subliminal: Subliminal()
        }
        self.initialized = self.validate()
        if not self.initialized:
            return

    def validate(self):
        return any(service.enabled for service in self.services.values())

    def run(self, item: MediaItem):
        if Subliminal.should_submit(item):
            self.services[Subliminal].run(item)
        yield item