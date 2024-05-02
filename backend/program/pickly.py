import os
import threading
import time

from program.media.container import MediaItemContainer


class Pickly(threading.Thread):
    def __init__(self, media_items: MediaItemContainer, data_path: str):
        super().__init__(name="Pickly")
        self.media_items = media_items
        self.data_path = data_path
        self.running = False
        self.save_interval = 60  # save media items every minute

    def start(self) -> None:
        self.running = True
        if len(self.media_items) == 0:
            self.load()
        super().start()

    def stop(self) -> None:
        self.running = False
        self.save()  # Ensure final save on stop
        if self.is_alive():
            self.join()

    def load(self) -> None:
        try:
            self.media_items.load(os.path.join(self.data_path, "media.pkl"))
        except Exception:
            raise

    def save(self) -> None:
        try:
            if len(self.media_items) > 0:
                self.media_items.save(os.path.join(self.data_path, "media.pkl"))
        except Exception:
            raise

    def run(self):
        while self.running:
            time.sleep(self.save_interval)
            self.save()
