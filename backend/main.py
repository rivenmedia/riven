import argparse
import contextlib
import sys
import threading
import time
import traceback

import uvicorn
from controllers.default import router as default_router
from controllers.items import router as items_router
from controllers.settings import router as settings_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from program import Program
from utils.logger import logger

parser = argparse.ArgumentParser()
parser.add_argument(
    "--ignore_cache",
    action="store_true",
    help="Ignore the cached metadata, create new data from scratch.",
)

args = parser.parse_args()

app = FastAPI()
app.program = Program(args)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(default_router)
app.include_router(settings_router)
app.include_router(items_router)


class Server(uvicorn.Server):
    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def run_in_thread(self):
        thread = threading.Thread(target=self.run, name="Iceberg")
        thread.start()
        try:
            while not self.started:
                time.sleep(1e-3)
            yield
        except Exception as e:
            logger.error(traceback.format_exc())
            logger.critical("Error in server thread: %s", e)
            raise e
        finally:
            app.program.stop()
            self.should_exit = True
            sys.exit(0)

config = uvicorn.Config(app, host="0.0.0.0", port=8080)
server = Server(config=config)


with server.run_in_thread():
    try:
        app.program.start()
        app.program.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.critical("Error in main thread: %s", e)
    finally:
        logger.info("Shutting down server.")
        sys.exit(0)