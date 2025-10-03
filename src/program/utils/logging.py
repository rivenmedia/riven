"""Logging utils"""

import os
import sys
from datetime import datetime

from loguru import logger

from program.settings.manager import settings_manager
from program.utils import data_dir_path


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

    # TRACE: 5
    # DEBUG: 10
    # INFO: 20
    # SUCCESS: 25
    # WARNING: 30
    # ERROR: 40
    # CRITICAL: 50

    log_levels = {
        "PROGRAM": (20, "cc6600", "🤖"),
        "DATABASE": (5, "d834eb", "🛢️"), # trace
        "DEBRID": (20, "cc3333", "🔗"),
        "FILESYSTEM": (5, "F9E79F", "🔗"), # trace
        "VFS": (5, "9B59B6", "🧲"), # trace
        "FUSE": (5, "999999", "⚙️"), # trace

        "SCRAPER": (20, "3D5A80", "👻"),
        "COMPLETED": (20, "FFFFFF", "🟢"),
        "CACHE": (5, "527826", "📜"), # trace
        "NOT_FOUND": (20, "818589", "🤷‍"),
        "NEW": (20, "ce7fab", "✨"),
        "FILES": (20, "FFFFE0", "🗃️ "),
        "ITEM": (20, "92a1cf", "🗃️ "),
        "DISCOVERY": (20, "e56c49", "🔍"),
        "API": (10, "006989", "👾"), # debug
        "PLEX": (20, "DAD3BE", "📽️ "),
        "LOCAL": (20, "DAD3BE", "📽️ "),
        "JELLYFIN": (20, "DAD3BE", "📽️ "),
        "EMBY": (20, "DAD3BE", "📽️ "),
        "TRAKT": (20, "006989", "🍿"),
    }

    # Set log levels
    for name, (no, default_color, default_icon) in log_levels.items():
        color, icon = get_log_settings(name, default_color, default_icon)
        logger.level(name, no=no, color=color, icon=icon)

    # Default log levels
    debug_color, debug_icon = get_log_settings("DEBUG", "98C1D9", "🐞")
    trace_color, trace_icon = get_log_settings("TRACE", "27F5E7", "✏️ ")
    info_color, info_icon = get_log_settings("INFO", "818589", "📰")
    warning_color, warning_icon = get_log_settings("WARNING", "ffcc00", "⚠️ ")
    critical_color, critical_icon = get_log_settings("CRITICAL", "ff0000", "")
    success_color, success_icon = get_log_settings("SUCCESS", "00ff00", "✔️ ")

    logger.level("DEBUG", color=debug_color, icon=debug_icon)
    logger.level("INFO", color=info_color, icon=info_icon)
    logger.level("WARNING", color=warning_color, icon=warning_icon)
    logger.level("CRITICAL", color=critical_color, icon=critical_icon)
    logger.level("SUCCESS", color=success_color, icon=success_icon)
    logger.level("TRACE", color=trace_color, icon=trace_icon)

    # Log format to match the old log format, but with color
    log_format = (
        "<fg #818589>{time:YY-MM-DD} {time:HH:mm:ss}</fg #818589> | "
        "<level>{level.icon}</level> <level>{level: <9}</level> | "
        "<fg #e7e7e7>{module}</fg #e7e7e7>.<fg #e7e7e7>{function}</fg #e7e7e7> - <level>{message}</level>"
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


setup_logger(settings_manager.settings.debug)