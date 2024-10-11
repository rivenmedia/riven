import psutil
import os
import time

from loguru import logger

limiter_enabled = os.getenv("RIVEN_ENABLE_MEMORY_LIMITER", "false").lower() in ["true", "1"]
log_enabled = os.getenv("RIVEN_LOG_MEMORY_USAGE", "true").lower() in ["true", "1"]

try:
    mem_limit = int(os.getenv("RIVEN_MEMORY_USAGE_LIMIT", "2048")) # 2GB Memory Limit
except ValueError:
    logger.warning("Invalid memory limit value. Using default of 2048 MB.")
    mem_limit = 2048

process = psutil.Process(os.getpid())


def check_memory_limit() -> bool:
    """
    Check if the current process's memory usage is below the specified limit.

    Returns:
        bool: True if memory usage is below the limit, False otherwise.
    """
    memory_usage_mb = process.memory_info().rss / (1024 * 1024)
    logger.debug(f"Current memory usage: {memory_usage_mb:.2f} MB")
    if limiter_enabled:
        return memory_usage_mb < mem_limit
    return True

def get_memory_usage() -> float:
    """Get the current memory usage of the process in megabytes."""
    return process.memory_info().rss / (1024 * 1024)

def log_memory_usage():
    """Log the current memory usage of the process."""
    memory_usage_mb = process.memory_info().rss / (1024 * 1024)
    logger.debug(f"Current memory usage: {memory_usage_mb:.2f} MB")

def wait_for_memory(check_interval=5):
    """
    Wait until the memory usage is below the specified limit.

    Args:
        check_interval (int): The interval in seconds to wait between memory checks.
    """
    if limiter_enabled and not check_memory_limit():
        if log_enabled:
            logger.warning(f"Memory usage exceeded {mem_limit} MB. Pausing processing.")
            log_memory_usage()
        while not check_memory_limit():
            time.sleep(check_interval)
        if log_enabled:
            logger.info("Memory usage is now below the limit. Resuming processing.")