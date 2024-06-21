import argparse
import contextlib
import os
import signal
import sys
import threading
import time
import traceback

import uvicorn
from controllers.default import router as default_router
from controllers.items import router as items_router
from controllers.metrics import router as metrics_router
from controllers.settings import router as settings_router
from controllers.tmdb import router as tmdb_router
from controllers.webhooks import router as webhooks_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from program import Program
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from utils.logger import logger


class LoguruMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            logger.exception(f"Exception during request processing: {e}")
            raise
        finally:
            process_time = time.time() - start_time
            logger.log(
                "API",
                f"{request.method} {request.url.path} - {response.status_code if 'response' in locals() else '500'} - {process_time:.2f}s",
            )
        return response


parser = argparse.ArgumentParser()
parser.add_argument(
    "--ignore_cache",
    action="store_true",
    help="Ignore the cached metadata, create new data from scratch.",
)

args = parser.parse_args()

app = FastAPI(
    title="Riven",
    summary="A media management system.",
    version="0.7.x",
    redoc_url=None,
    license_info={
        "name": "GPL-3.0",
        "url": "https://www.gnu.org/licenses/gpl-3.0.en.html",
    },
)
app.program = Program(args)

app.add_middleware(LoguruMiddleware)
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
app.include_router(webhooks_router)
app.include_router(tmdb_router)
app.include_router(metrics_router)


class Server(uvicorn.Server):
    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def run_in_thread(self):
        thread = threading.Thread(target=self.run, name="Riven")
        thread.start()
        try:
            while not self.started:
                time.sleep(1e-3)
            yield
        except Exception as e:
            logger.error(f"Error in server thread: {e}")
            logger.exception(traceback.format_exc())
            raise e
        finally:
            self.should_exit = True
            sys.exit(0)

def signal_handler(sig, frame):
    logger.log('PROGRAM','Exiting Gracefully.')
    app.program.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_config=None)
server = Server(config=config)

with server.run_in_thread():
    try:
        app.program.start()
        app.program.run()
    except Exception as e:
        logger.error(f"Error in main thread: {e}")
        logger.exception(traceback.format_exc())
    finally:
        logger.critical("Server has been stopped")
        sys.exit(0)