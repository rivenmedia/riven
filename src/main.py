from collections.abc import Awaitable, Callable
import contextlib
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from types import FrameType

from kink import di
import uvicorn
from dotenv import load_dotenv

load_dotenv()  # import required here to support SETTINGS_FILENAME

from program.utils.proxy_client import ProxyClient
from program.utils.async_client import AsyncClient

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from scalar_fastapi import (
    get_scalar_api_reference,  # pyright: ignore[reportUnknownVariableType]
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from program.apis import bootstrap_apis
from program.program import Program, riven
from program.settings.models import get_version
from program.settings import settings_manager
from program.utils.cli import handle_args
from routers import app_router


def _apache_log_line(
    client_host: str,
    ident: str,
    auth_user: str,
    timestamp: str,
    request_line: str,
    status: int,
    bytes_sent: str,
    referer: str,
    user_agent: str,
) -> str:
    """Apache Combined Log Format: %h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-Agent}i" """
    return f'{client_host} {ident} {auth_user} [{timestamp}] "{request_line}" {status} {bytes_sent} "{referer}" "{user_agent}"'


class LoguruMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, log_requests: bool = True) -> None:
        super().__init__(app)
        self.log_requests = log_requests

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = None

        try:
            response = await call_next(request)
            return response
        except Exception as e:
            logger.exception(f"Exception during request processing: {e}")
            raise
        finally:
            client = getattr(request, "client", None)
            client_host = client[0] if client else "-"
            ident = "-"
            auth_user = "-"
            ts = datetime.now(timezone.utc).strftime("%d/%b/%Y:%H:%M:%S +0000")
            path = request.url.path
            if request.url.query:
                path = f"{path}?{request.url.query}"
            request_line = f"{request.method} {path} HTTP/1.1"
            status = response.status_code if response else 500
            cl = response.headers.get("content-length", "-") if response else "-"
            referer = request.headers.get("referer", "-") or "-"
            user_agent = request.headers.get("user-agent", "-") or "-"

            if self.log_requests:
                log_line = _apache_log_line(
                    client_host, ident, auth_user, ts, request_line, status, cl, referer, user_agent
                )
                logger.info(log_line)


args = handle_args()

# Register API services so they are available in the process that serves HTTP
# (e.g. uvicorn reload worker). Program also calls this on start.
bootstrap_apis()


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    di[AsyncClient] = AsyncClient()

    proxy_url = settings_manager.settings.downloaders.proxy_url

    if proxy_url:
        di[ProxyClient] = ProxyClient(proxy_url=proxy_url)

    yield

    await di[AsyncClient].aclose()

    if ProxyClient in di:
        await di[ProxyClient].aclose()


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


src_dir = Path(__file__).parent
frontend_index = src_dir / "static" / "ui" / "index.html"
frontend_assets_dir = src_dir / "static" / "ui"

app.mount(
    "/static/ui",
    StaticFiles(directory=str(frontend_assets_dir), check_dir=False),
    name="static-ui",
)


@app.get("/", include_in_schema=False)
async def homepage():
    if not frontend_index.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend bundle missing. Run `make frontend-build`.",
        )
    return FileResponse(frontend_index)


di[Program] = riven

app.add_middleware(LoguruMiddleware, log_requests=settings_manager.settings.log_requests)
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


def signal_handler(signum: int, frame: FrameType | None):
    logger.log("PROGRAM", "Exiting Gracefully.")
    di[Program].stop()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    if getattr(args, "reload", False):
        def _run_program() -> None:
            try:
                di[Program].start()
                di[Program].run()
            except Exception:
                logger.exception("Error in Program thread")

        _program_thread = threading.Thread(target=_run_program, name="Program", daemon=True)
        _program_thread.start()
        uvicorn.run(
            "src.main:app",
            host="0.0.0.0",
            port=args.port,
            log_config=None,
            reload=True,
        )
    else:
        config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_config=None)
        server = Server(config=config)

        with server.run_in_thread():
            try:
                di[Program].start()
                di[Program].run()
            except Exception:
                logger.exception("Error in main thread")
            finally:
                logger.critical("Server has been stopped")
                sys.exit(0)
