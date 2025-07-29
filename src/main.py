import contextlib
import signal
import sys
import threading
import time
import traceback
from collections import defaultdict, deque
from typing import Dict, List

import uvicorn
from dotenv import load_dotenv
load_dotenv() # import required here to support SETTINGS_FILENAME

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from scalar_fastapi import get_scalar_api_reference
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from program import Program
from program.settings.models import get_version
from program.utils.cli import handle_args
from routers import app_router


class PerformanceMonitor:
    """Performance monitoring and metrics collection."""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.request_times = defaultdict(lambda: deque(maxlen=max_samples))
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.slow_requests = deque(maxlen=100)  # Keep track of slowest requests
        self._lock = threading.RLock()

    def record_request(self, method: str, path: str, duration: float, status_code: int):
        """Record a request's performance metrics."""
        with self._lock:
            endpoint = f"{method} {path}"

            # Record timing
            self.request_times[endpoint].append(duration)
            self.request_counts[endpoint] += 1

            # Record errors
            if status_code >= 400:
                self.error_counts[endpoint] += 1

            # Track slow requests (>2 seconds)
            if duration > 2.0:
                self.slow_requests.append({
                    'endpoint': endpoint,
                    'duration': duration,
                    'status_code': status_code,
                    'timestamp': time.time()
                })

    def get_stats(self) -> Dict:
        """Get performance statistics."""
        with self._lock:
            stats = {}

            for endpoint, times in self.request_times.items():
                if times:
                    times_list = list(times)
                    stats[endpoint] = {
                        'count': self.request_counts[endpoint],
                        'avg_time': sum(times_list) / len(times_list),
                        'min_time': min(times_list),
                        'max_time': max(times_list),
                        'error_count': self.error_counts[endpoint],
                        'error_rate': self.error_counts[endpoint] / self.request_counts[endpoint] if self.request_counts[endpoint] > 0 else 0
                    }

            return {
                'endpoints': stats,
                'slow_requests': list(self.slow_requests)[-10:],  # Last 10 slow requests
                'total_requests': sum(self.request_counts.values()),
                'total_errors': sum(self.error_counts.values())
            }


# Global performance monitor
performance_monitor = PerformanceMonitor()


class LoguruMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            logger.exception(f"Exception during request processing: {e}")
            raise
        finally:
            process_time = time.time() - start_time

            # Record performance metrics
            performance_monitor.record_request(
                request.method,
                request.url.path,
                process_time,
                status_code
            )

            # Log with performance context
            log_level = "WARNING" if process_time > 2.0 else "API"
            logger.log(
                log_level,
                f"{request.method} {request.url.path} - {status_code} - {process_time:.2f}s",
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
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )

app.program = Program()
app.performance_monitor = performance_monitor  # Make performance monitor accessible to routes
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
        except Exception as e:
            logger.error(f"Error in server thread: {e}")
            logger.exception(traceback.format_exc())
            raise e
        finally:
            self.should_exit = True
            sys.exit(0)

def signal_handler(signum, frame):
    logger.log("PROGRAM","Exiting Gracefully.")
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
    except Exception as e:
        logger.error(f"Error in main thread: {e}")
        logger.exception(traceback.format_exc())
    finally:
        logger.critical("Server has been stopped")
        sys.exit(0)
