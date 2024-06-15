import os
import threading

from program.media.container import MediaItemContainer


class Pickly(threading.Thread):
    def __init__(self, media_items: MediaItemContainer, data_path: str):
        super().__init__(name="Pickly")
        self.media_items = media_items
        self.data_path = data_path
        self.media_file = os.path.join(self.data_path, "media.pkl")
        self.running = False
        self._stop_event = threading.Event()

    def start(self) -> None:
        self.running = True
        super().start()

    def stop(self) -> None:
        self.running = False
        self._stop_event.set()
        self.save()

    def join(self, timeout=None) -> None:
        self.stop()
        super().join(timeout)

    def load(self) -> None:
        self.media_items.load(self.media_file)

    def save(self) -> None:
        self.media_items.save(self.media_file)

    def run(self):
        while self.running:
            self.save()
            self._stop_event.wait(60)
