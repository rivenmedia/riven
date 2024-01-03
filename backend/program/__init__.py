"""Program main module"""
import threading
import time
from program.scrapers import Scraping
from program.realdebrid import Debrid
from program.symlink import Symlinker
from program.media.container import MediaItemContainer
from utils.logger import logger, get_data_path
from program.plex import Plex
from program.content import Content
from utils.utils import Pickly
from utils.settings import settings_manager as settings
import concurrent.futures
from utils.service_manager import ServiceManager


class Program(threading.Thread):
    """Program class"""

    def __init__(self):
        super().__init__(name="Iceberg")
        self.running = False

    def start(self):
        logger.info("Iceberg starting!")
        self.media_items = MediaItemContainer(items=[])
        self.data_path = get_data_path()
        self.pickly = Pickly(self.media_items, self.data_path)
        self.pickly.start()
        self.core_manager = ServiceManager(self.media_items, Content, Plex)
        for service in self.core_manager.services:
            service.start()
        self.extras_manager = ServiceManager(None, Scraping, Debrid, Symlinker)
        super().start()
        self.running = True
        logger.info("Iceberg started!")

    def run(self):
        while self.running:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=10, thread_name_prefix="Worker"
            ) as executor:
                for item in self.media_items:
                    executor.submit(item.perform_action, self.core_manager.services + self.extras_manager.services)
            time.sleep(2)

    def stop(self):
        for thread in self.threads:
            thread.stop()
        self.pickly.stop()
        settings.save()
        self.running = False
