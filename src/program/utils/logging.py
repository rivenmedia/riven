"""Enhanced logging utilities with performance monitoring and structured logging"""

import os
import sys
import time
import threading
import traceback
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import Any, Dict, Optional, Union

from loguru import logger
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from program.settings.manager import settings_manager
from program.utils import data_dir_path

LOG_ENABLED: bool = settings_manager.settings.log

def setup_logger(level):
    """Setup the logger"""
    logs_dir_path = data_dir_path / "logs"
    os.makedirs(logs_dir_path, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    log_filename = logs_dir_path / f"riven-{timestamp}.log"

    # Helper function to get log settings from environment or use default
    def get_log_settings(name, default_color, default_icon):
        color = os.getenv(f"RIVEN_LOGGER_{name}_FG", default_color)
        icon = os.getenv(f"RIVEN_LOGGER_{name}_ICON", default_icon)
        return f"<fg #{color}>", icon

    # Define log levels and their default settings
    log_levels = {
        "PROGRAM": (36, "cc6600", "🤖"),
        "DATABASE": (37, "d834eb", "🛢️"),
        "DEBRID": (38, "cc3333", "🔗"),
        "SYMLINKER": (39, "F9E79F", "🔗"),
        "SCRAPER": (40, "3D5A80", "👻"),
        "COMPLETED": (41, "FFFFFF", "🟢"),
        "CACHE": (42, "527826", "📜"),
        "NOT_FOUND": (43, "818589", "🤷‍"),
        "NEW": (44, "e63946", "✨"),
        "FILES": (45, "FFFFE0", "🗃️ "),
        "ITEM": (46, "92a1cf", "🗃️ "),
        "DISCOVERY": (47, "e56c49", "🔍"),
        "API": (10, "006989", "👾"),
        "PLEX": (47, "DAD3BE", "📽️ "),
        "LOCAL": (48, "DAD3BE", "📽️ "),
        "JELLYFIN": (48, "DAD3BE", "📽️ "),
        "EMBY": (48, "DAD3BE", "📽️ "),
        "TRAKT": (48, "1DB954", "🎵"),
        # Enhanced logging levels
        "PERFORMANCE": (49, "ff6b35", "⚡"),  # Performance metrics
        "MEMORY": (50, "f72585", "🧠"),       # Memory usage tracking
        "QUEUE": (51, "4361ee", "📋"),        # Queue operations
        "SESSION": (52, "7209b7", "🔐"),      # Database sessions
        "STREAM": (53, "560bad", "🌊"),       # Stream processing
        "STATE": (54, "480ca8", "🔄"),        # State transitions
        "WEBHOOK": (55, "3a0ca3", "🪝"),      # Webhook events
        "BATCH": (56, "7b2cbf", "📦"),        # Batch operations
        "CLEANUP": (57, "5a189a", "🧹"),      # Cleanup operations
        "HEALTH": (58, "240046", "❤️"),       # Health checks
    }

    # Set log levels
    for name, (no, default_color, default_icon) in log_levels.items():
        color, icon = get_log_settings(name, default_color, default_icon)
        logger.level(name, no=no, color=color, icon=icon)

    # Default log levels
    debug_color, debug_icon = get_log_settings("DEBUG", "98C1D9", "🐞")
    info_color, info_icon = get_log_settings("INFO", "818589", "📰")
    warning_color, warning_icon = get_log_settings("WARNING", "ffcc00", "⚠️ ")
    critical_color, critical_icon = get_log_settings("CRITICAL", "ff0000", "")
    success_color, success_icon = get_log_settings("SUCCESS", "00ff00", "✔️ ")

    logger.level("DEBUG", color=debug_color, icon=debug_icon)
    logger.level("INFO", color=info_color, icon=info_icon)
    logger.level("WARNING", color=warning_color, icon=warning_icon)
    logger.level("CRITICAL", color=critical_color, icon=critical_icon)
    logger.level("SUCCESS", color=success_color, icon=success_icon)

    # Log format to match the old log format, but with color
    log_format = (
        "<fg #818589>{time:YY-MM-DD} {time:HH:mm:ss}</fg #818589> | "
        "<level>{level.icon}</level> <level>{level: <9}</level> | "
        "<fg #990066>{module}</fg #990066>.<fg #990066>{function}</fg #990066> - <level>{message}</level>"
    )

    logger.configure(handlers=[
        {
            "sink": sys.stderr,
            "level": level.upper() or "INFO",
            "format": log_format,
            "backtrace": False,
            "diagnose": False,
            "enqueue": True,
        },
        {
            "sink": log_filename,
            "level": level.upper(),
            "format": log_format,
            "rotation": "25 MB",
            "retention": "24 hours",
            "compression": None,
            "backtrace": False,
            "diagnose": True,
            "enqueue": True,
        }
    ])

def log_cleaner():
    """Remove old log files based on retention settings, leaving the most recent one."""
    cleaned = False
    try:
        logs_dir_path = data_dir_path / "logs"
        log_files = sorted(logs_dir_path.glob("riven-*.log"), key=lambda x: x.stat().st_mtime)
        for log_file in log_files[:-1]:
            # remove files older than 8 hours
            if (datetime.now() - datetime.fromtimestamp(log_file.stat().st_mtime)).total_seconds() / 3600 > 8:
                log_file.unlink()
                cleaned = True
        if cleaned:
            logger.debug("Cleaned up old logs that were older than 8 hours.")
    except Exception as e:
        logger.error(f"Failed to clean old logs: {e}")

class PerformanceLogger:
    """Enhanced performance logging with timing and memory tracking."""

    def __init__(self):
        self.timings = {}
        self.counters = {}
        self.lock = threading.RLock()

    def time_operation(self, operation_name: str, duration: float, context: Dict[str, Any] = None):
        """Log operation timing with context."""
        with self.lock:
            if operation_name not in self.timings:
                self.timings[operation_name] = []
            self.timings[operation_name].append(duration)

            # Keep only last 100 timings per operation
            if len(self.timings[operation_name]) > 100:
                self.timings[operation_name] = self.timings[operation_name][-100:]

        # Log slow operations
        if duration > 2.0:  # Slower than 2 seconds
            level = "WARNING" if duration > 5.0 else "PERFORMANCE"
            context_str = f" | {context}" if context else ""
            logger.log(level, f"Slow operation: {operation_name} took {duration:.2f}s{context_str}")
        elif duration > 0.5:  # Slower than 500ms
            context_str = f" | {context}" if context else ""
            logger.log("PERFORMANCE", f"{operation_name} took {duration:.2f}s{context_str}")

    def increment_counter(self, counter_name: str, value: int = 1):
        """Increment a named counter."""
        with self.lock:
            self.counters[counter_name] = self.counters.get(counter_name, 0) + value

    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        with self.lock:
            stats = {
                'timings': {},
                'counters': dict(self.counters)
            }

            for operation, times in self.timings.items():
                if times:
                    stats['timings'][operation] = {
                        'count': len(times),
                        'avg': sum(times) / len(times),
                        'min': min(times),
                        'max': max(times),
                        'recent': times[-10:]  # Last 10 timings
                    }

            return stats


# Global performance logger instance
perf_logger = PerformanceLogger()


def log_performance(operation_name: str = None, log_args: bool = False, log_result: bool = False):
    """
    Decorator to log function performance and execution details.

    Args:
        operation_name: Custom name for the operation (defaults to function name)
        log_args: Whether to log function arguments
        log_result: Whether to log function result
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            start_time = time.time()

            # Log function entry
            context = {}
            if log_args and (args or kwargs):
                context['args'] = str(args)[:200] if args else None
                context['kwargs'] = str(kwargs)[:200] if kwargs else None

            logger.log("PERFORMANCE", f"Starting {op_name}")

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Log successful completion
                if log_result and result is not None:
                    context['result'] = str(result)[:200]

                perf_logger.time_operation(op_name, duration, context)
                logger.log("PERFORMANCE", f"Completed {op_name} in {duration:.3f}s")

                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"Failed {op_name} after {duration:.3f}s: {e}")
                perf_logger.time_operation(f"{op_name}_failed", duration, {'error': str(e)})
                raise

        return wrapper
    return decorator


@contextmanager
def log_context(context_name: str, level: str = "DEBUG", log_entry: bool = True, log_exit: bool = True):
    """
    Context manager for logging entry/exit of code blocks with timing.

    Args:
        context_name: Name of the context
        level: Log level to use
        log_entry: Whether to log context entry
        log_exit: Whether to log context exit
    """
    start_time = time.time()

    if log_entry:
        logger.log(level, f"Entering {context_name}")

    try:
        yield
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Exception in {context_name} after {duration:.3f}s: {e}")
        raise
    finally:
        if log_exit:
            duration = time.time() - start_time
            logger.log(level, f"Exiting {context_name} after {duration:.3f}s")


def log_memory_usage(operation: str, level: str = "MEMORY"):
    """Log current memory usage for an operation."""
    try:
        import psutil
        import os

        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        logger.log(level, f"{operation} | Memory usage: {memory_mb:.1f}MB")

    except ImportError:
        logger.debug(f"{operation} | Memory logging unavailable (psutil not installed)")
    except Exception as e:
        logger.debug(f"{operation} | Memory logging failed: {e}")


def log_database_operation(operation: str, query: str = None, duration: float = None,
                          rows_affected: int = None, level: str = "DATABASE"):
    """Log database operations with context."""
    context_parts = [operation]

    if duration is not None:
        context_parts.append(f"{duration:.3f}s")

    if rows_affected is not None:
        context_parts.append(f"{rows_affected} rows")

    if query and len(query) < 200:
        context_parts.append(f"Query: {query}")
    elif query:
        context_parts.append(f"Query: {query[:200]}...")

    logger.log(level, " | ".join(context_parts))


def log_api_request(method: str, url: str, status_code: int = None,
                   duration: float = None, level: str = "API"):
    """Log API requests with timing and status."""
    context_parts = [f"{method} {url}"]

    if status_code is not None:
        context_parts.append(f"Status: {status_code}")

    if duration is not None:
        context_parts.append(f"{duration:.3f}s")

    # Use different levels based on status code
    if status_code and status_code >= 400:
        level = "WARNING" if status_code < 500 else "ERROR"
    elif duration and duration > 5.0:
        level = "WARNING"

    logger.log(level, " | ".join(context_parts))


def log_queue_operation(operation: str, queue_size: int = None, item_id: str = None,
                       level: str = "QUEUE"):
    """Log queue operations with context."""
    context_parts = [operation]

    if queue_size is not None:
        context_parts.append(f"Queue size: {queue_size}")

    if item_id:
        context_parts.append(f"Item: {item_id}")

    logger.log(level, " | ".join(context_parts))


def log_session_operation(operation: str, session_id: str = None, duration: float = None,
                         level: str = "SESSION"):
    """Log database session operations."""
    context_parts = [operation]

    if session_id:
        context_parts.append(f"Session: {session_id}")

    if duration is not None:
        context_parts.append(f"{duration:.3f}s")

    logger.log(level, " | ".join(context_parts))


def create_progress_bar() -> tuple[Progress, Console]:
    """Create a rich progress bar for operations."""
    console = Console()
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TextColumn("[progress.completed]{task.completed}/{task.total}", justify="right"),
        TextColumn("[progress.log]{task.fields[log]}", justify="right"),
        console=console,
        transient=True
    )
    return progress, console


# Initialize logging
console = Console()
log_level = "DEBUG" if settings_manager.settings.debug else "INFO"
setup_logger(log_level)