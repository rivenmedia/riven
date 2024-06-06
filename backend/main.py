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
            logger.exception(traceback.format_exc())
            logger.exception(f"Error in server thread: {e}")
            raise e
        finally:
            self.should_exit = True

config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_config=None)
server = Server(config=config)


with server.run_in_thread():
    try:
        app.program.start()
        app.program.run()
    except AttributeError as e:
        logger.error(f"Program failed to initialize: {e}")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.exception(f"Error in main thread: {e}")
    finally:
        app.program.stop()
        logger.critical("Server has been stopped")
        sys.exit(0)