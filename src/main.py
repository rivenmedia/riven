import contextlib
import signal
import sys
import threading
import time

import httpx
import uvicorn
from dotenv import load_dotenv
from kink import di

load_dotenv()  # import required here to support SETTINGS_FILENAME

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from scalar_fastapi import get_scalar_api_reference
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from program.db.db import db  # noqa
from program.program import riven
from program.settings.models import get_version
from program.utils.cli import handle_args
from routers import app_router


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


args = handle_args()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    # Create AsyncClient with limited connection pools to prevent overwhelming debrid services
    # Limits: 10 connections per host, 20 total connections, prevent connection pool exhaustion
    limits = httpx.Limits(
        max_connections=20,
        max_keepalive_connections=10,
        keepalive_expiry=30.0,
    )
    di[httpx.AsyncClient] = httpx.AsyncClient(
        http2=True,
        limits=limits,
        timeout=httpx.Timeout(30.0),  # 30 second timeout for all requests
    )
    yield
    await di[httpx.AsyncClient].aclose()


app = FastAPI(
    title="Riven",
    summary="A media management system.",
    version=get_version(),
    redoc_url=None,
    license_info={
        "name": "GPL-3.0",
        "url": "https://www.gnu.org/licenses/gpl-3.0.en.html",
    },
    lifespan=lifespan,
)


@app.get("/scalar", include_in_schema=False)
async def scalar_html():
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
        except Exception:
            logger.exception("Error in server thread")
            raise
        finally:
            self.should_exit = True
            sys.exit(0)


def signal_handler(signum, frame):
    logger.log("PROGRAM", "Exiting Gracefully.")
    app.program.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_config=None)
server = Server(config=config)


with server.run_in_thread():
    try:
        app.program.start()
        app.program.run()
    except Exception:
        logger.exception("Error in main thread")
    finally:
        logger.critical("Server has been stopped")
        sys.exit(0)
