import os
import threading
import time


class Pickly(threading.Thread):
    def __init__(self, media_items, data_path: str):
        super().__init__(name="Pickly")
        self.media_items = media_items
        self.data_path = data_path
        self.running = False

    def start(self) -> None:
        self.load()
        self.running = True
        return super().start()

    def stop(self) -> None:
        self.save()
        self.running = False

    def load(self) -> None:
        self.media_items.load(os.path.join(self.data_path, "media.pkl"))

    def save(self) -> None:
        self.media_items.save(os.path.join(self.data_path, "media.pkl"))

    def run(self):
        while self.running:
            self.save()
            # workaround for quick shutdown, we should use threading.Event instead
            for i in range(10):
                if not self.running:
                    break
                time.sleep(i)
