"""Main entry point for the Riven application."""
import contextlib
import signal
import sys
import threading
import time
import traceback

import uvicorn
from dotenv import load_dotenv

load_dotenv()  # Import required here to support SETTINGS_FILENAME

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from scalar_fastapi import get_scalar_api_reference
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from program.program import riven
from program.settings.models import get_version
from program.utils.cli import handle_args
from routers import app_router


class LoguruMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests with timing information."""

    async def dispatch(self, request: Request, call_next):
        """Process request and log timing information."""
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

args = handle_args()

app = FastAPI(
    title="Riven",
    summary="A media management system.",
    version=get_version(),
    redoc_url=None,
    license_info={
        "name": "GPL-3.0",
        "url": "https://www.gnu.org/licenses/gpl-3.0.en.html",
    },
)

@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    """Serve Scalar API documentation."""
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )

app.program = riven
app.add_middleware(LoguruMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_router)

class Server(uvicorn.Server):
    """Custom Uvicorn server that runs in a separate thread."""

    def install_signal_handlers(self):
        """Override to prevent Uvicorn from installing its own signal handlers."""
        pass

    @contextlib.contextmanager
    def run_in_thread(self):
        """Run the server in a background thread."""
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

def signal_handler(signum, frame):
    """Handle SIGINT and SIGTERM signals for graceful shutdown."""
    logger.log("PROGRAM", "Exiting Gracefully.")
    app.program.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_config=None)
server = Server(config=config)

with server.run_in_thread():
    try:
        app.program.start(dev_reset_db=getattr(args, 'dev_reset_db', False))
        app.program.run()
    except Exception as e:
        logger.error(f"Error in main thread: {e}")
        logger.exception(traceback.format_exc())
    finally:
        logger.critical("Server has been stopped")
        sys.exit(0)
