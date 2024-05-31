import argparse
import asyncio
import contextlib
import os
import signal
import sys
import threading
import time
import traceback
import uvicorn

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from controllers.default import router as default_router
from controllers.items import router as items_router
from controllers.settings import router as settings_router
from program import Program
from utils.logger import logger

# Configuration for the application
def load_config():
    parser = argparse.ArgumentParser(description="Run the Iceberg server.")
    parser.add_argument("--ignore_cache", action="store_true", help="Ignore the cached metadata, create new data from scratch.")
    return parser.parse_args()

# Application setup
def create_app(args):
    app = FastAPI(title="Iceberg API")
    app.program = Program(args)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )
    app.include_router(default_router)
    app.include_router(settings_router)
    app.include_router(items_router)
    return app

# Server configuration
class Server(uvicorn.Server):
    def install_signal_handlers(self):
        """Override to customize signal handling."""
        pass

    @contextlib.contextmanager
    def run_in_thread(self):
        thread = threading.Thread(target=self.run, name="Iceberg")
        thread.start()
        try:
            while not self.started:
                time.sleep(0.001)
            yield
        except Exception as e:
            logger.exception("Error in server thread: %s", e)
            raise
        finally:
            self.should_exit = True

# Main application class
class Application:
    def __init__(self, app, server):
        self.app = app
        self.server = server
        self.shutdown_event = threading.Event()

    def run(self):
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

        with self.server.run_in_thread():
            try:
                self.app.program.start()
                asyncio.run(self.app.program.run())
                self.app.program.join()
            except Exception as e:
                logger.exception("Error in main thread: %s", e)
            finally:
                logger.critical("Server has been shut down.")
                self.shutdown_program()
                sys.exit(0)

    def handle_signal(self, signum, frame):
        logger.critical("Received termination signal. Shutting down server.")
        self.shutdown_event.set()
        self.shutdown_program()

    def shutdown_program(self):
        if self.shutdown_event.is_set():
            return
        self.shutdown_event.set()
        try:
            asyncio.run(self.app.program.stop())
        except Exception as e:
            logger.exception("Error during shutdown: %s", e)
        finally:
            logger.info("Flushing and closing logger.")
            logger.complete()
            for thread in threading.enumerate():
                if thread is not threading.main_thread():
                    thread.join()
            sys.exit(0)

# Entry point
if __name__ == "__main__":
    args = load_config()
    app = create_app(args)
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_config=None)
    server = Server(config=config)
    application = Application(app, server)
    application.run()