import psutil
import os
import time

from program.settings.manager import settings_manager
from loguru import logger

limiter_enabled = os.getenv("RIVEN_ENABLE_MEMORY_LIMITER", "false").lower() in ["true", "1"]
log_enabled = os.getenv("RIVEN_LOG_MEMORY_USAGE", "true").lower() in ["true", "1"]

try:
    mem_limit = int(os.getenv("RIVEN_MEMORY_USAGE_LIMIT", "1024")) # 1GB Memory Limit
except ValueError:
    mem_limit = 1024

process = psutil.Process(os.getpid())


def check_memory_limit() -> bool:
    """
    Check if the current process's memory usage is below the specified limit.

    Returns:
        bool: True if memory usage is below the limit, False otherwise.
    """
    memory_usage_mb = process.memory_info().rss / (1024 * 1024)
    # enable this to see the fluctuations more for memory usage
    # logger.debug(f"Current memory usage of Riven process: {memory_usage_mb:.2f} MB")
    if limiter_enabled:
        return memory_usage_mb <= mem_limit
    return True

def get_memory_usage() -> float:
    """Get the current memory usage of the process in megabytes."""
    return process.memory_info().rss / (1024 * 1024)

def log_memory_usage():
    """Log the current memory usage of the process."""
    memory_usage_mb = process.memory_info().rss / (1024 * 1024)
    logger.debug(f"Current memory usage of Riven process: {memory_usage_mb:.2f} MB")

def wait_for_memory(check_interval=5):
    """
    Wait until the memory usage is below the specified limit.

    Args:
        check_interval (int): The interval in seconds to wait between memory checks.
    """
    if not check_memory_limit():
        if log_enabled:
            logger.warning(f"Memory usage exceeded {mem_limit} MB. Pausing processing.")
            if settings_manager.settings.tracemalloc:
                log_memory_usage()
        while not check_memory_limit():
            time.sleep(check_interval)
        if log_enabled:
            logger.info("Memory usage is now below the limit. Resuming processing.")

 # this isn't used anywhere yet, may have to tweak these

def estimate_object_size(obj: object) -> int:
    """Estimate the size of an object in bytes."""
    from pympler import asizeof
    return asizeof.asizeof(obj)

def log_object_size(obj: object, label: str = "Object"):
    """Log the size of an object in megabytes."""
    size = estimate_object_size(obj)
    logger.debug(f"{label} size: {size / (1024 * 1024):.2f} MB")

def log_memory_summary(objs: list[object] = None):
    """Log a summary of memory usage."""
    from pympler import muppy, summary
    all_objects = objs if objs else muppy.get_objects()
    mem_summary = summary.summarize(all_objects)
    summary.print_(mem_summary)
    log_memory_usage()
