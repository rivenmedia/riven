from collections.abc import Awaitable, Callable
import contextlib
import signal
import sys
import time
from types import FrameType

from kink import di
import trio
import trio_util
import uvicorn
from dotenv import load_dotenv

from program.utils.proxy_client import ProxyClient
from program.utils.async_client import AsyncClient
from program.utils.nursery import Nursery

load_dotenv()  # import required here to support SETTINGS_FILENAME

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from scalar_fastapi import (
    get_scalar_api_reference,  # pyright: ignore[reportUnknownVariableType]
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from program.program import Program, riven
from program.settings.models import get_version
from program.settings import settings_manager
from program.utils.cli import handle_args
from routers import app_router


class LoguruMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start_time = time.time()
        response = None

        try:
            response = await call_next(request)

            return response
        except Exception as e:
            logger.exception(f"Exception during request processing: {e}")
            raise
        finally:
            process_time = time.time() - start_time

            logger.log(
                "API",
                f"{request.method} {request.url.path} - {response.status_code if response else '500'} - {process_time:.2f}s",
            )


args = handle_args()


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


di[Program] = riven

app.add_middleware(LoguruMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_router)


def signal_handler(signum: int, frame: FrameType | None):
    logger.log("PROGRAM", "Exiting Gracefully.")
    di[Program].stop()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

config = uvicorn.Config(app, host="0.0.0.0", port=args.port, log_config=None)
server = uvicorn.Server(config=config)


@contextlib.asynccontextmanager
async def server_lifecycle():
    async def _start_server():
        await trio.to_thread.run_sync(server.run)

    try:
        async with trio_util.run_and_cancelling(_start_server):
            await di[Program].start()

            yield
    except Exception:
        logger.exception("Error in server lifecycle")
    finally:
        logger.critical("Server is shutting down")


async def main():
    async with trio.open_nursery() as nursery:
        di[Nursery] = Nursery(nursery=nursery)

        async with server_lifecycle():
            async with trio_util.move_on_when(
                lambda: di[Program].initialized.wait_value(False)
            ):
                await di[Program].run()

    logger.critical("Server has been stopped")

    sys.exit(0)


trio.run(main)
