"""Program main module"""
import os
import threading
import time
import concurrent.futures
from program.scrapers import Scraping
from program.realdebrid import Debrid
from program.symlink import Symlinker
from program.media.container import MediaItemContainer
from utils.logger import logger
from program.plex import Plex
from program.content import Content
from utils.utils import Pickly
from utils import data_dir_path
from program.settings.manager import settings_manager
from utils.service_manager import ServiceManager


class Program(threading.Thread):
    """Program class"""

    def __init__(self, args):
        super().__init__(name="Iceberg")
        self.running = False
        self.startup_args = args
        logger.configure_logger(
            debug=settings_manager.settings.debug,
            log=settings_manager.settings.log
        )

    def start(self):
        logger.info("Iceberg v%s starting!", settings_manager.settings.version)
        self.initialized = False
        self.media_items = MediaItemContainer(items=[])
        self.data_path = data_dir_path
        os.makedirs(self.data_path, exist_ok=True)
        if not self.startup_args.dev:
            self.pickly = Pickly(self.media_items, self.data_path)
            self.pickly.start()
        self.core_manager = ServiceManager(self.media_items, True, Content, Plex, Scraping, Debrid, Symlinker)
        if self.validate():
            logger.info("Iceberg started!")
        else:
            logger.info("----------------------------------------------")
            logger.info("Iceberg is waiting for configuration to start!")
            logger.info("----------------------------------------------")
        super().start()
        self.running = True
        self.initialized = True

    def run(self):
        while self.running:
            if self.validate():
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=10, thread_name_prefix="Worker"
                ) as executor:
                    for item in self.media_items:
                        executor.submit(item.perform_action, self.core_manager.services)
            time.sleep(1)

    def validate(self):
        return all(service.initialized for service in self.core_manager.services)

    def stop(self):
        for service in self.core_manager.services:
            if getattr(service, "running", False):
                service.stop()
        self.pickly.stop()
        settings.save()
        self.running = False