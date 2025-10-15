"""Logging utils"""

import os
import sys
from datetime import datetime

from loguru import logger

from program.settings.manager import settings_manager
from program.utils import data_dir_path

LAST_LOGS_CLEANED: datetime | None = None


def setup_logger(level):
    """Setup the logger"""

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
        "DATABASE": (5, "d834eb", "🛢️"),  # trace
        "DEBRID": (20, "cc3333", "🔗"),
        "FILESYSTEM": (5, "F9E79F", "🔗"),  # trace
        "VFS": (5, "9B59B6", "🧲"),  # trace
        "FUSE": (5, "999999", "⚙️"),  # trace
        "SCRAPER": (20, "3D5A80", "👻"),
        "COMPLETED": (20, "FFFFFF", "🟢"),
        "CACHE": (5, "527826", "📜"),  # trace
        "NOT_FOUND": (20, "818589", "🤷‍"),
        "NEW": (20, "ce7fab", "✨"),
        "FILES": (20, "FFFFE0", "🗃️ "),
        "ITEM": (20, "92a1cf", "🗃️ "),
        "DISCOVERY": (20, "e56c49", "🔍"),
        "API": (10, "006989", "👾"),  # debug
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

    log_settings = settings_manager.settings.logging
    retention_value = (
        f"{log_settings.retention_hours} hours" if log_settings.enabled else None
    )
    rotation_value = (
        f"{getattr(log_settings, 'rotation_mb', 10)} MB"
        if getattr(log_settings, "rotation_mb", 10) > 0
        else None
    )
    compression_value = getattr(log_settings, "compression", "disabled")

    handlers = [
        {
            "sink": sys.stderr,
            "level": level.upper() or "INFO",
            "format": log_format,
            "backtrace": False,
            "diagnose": False,
            "enqueue": True,
        }
    ]

    if log_settings.enabled:
        logs_dir_path = data_dir_path / "logs"
        os.makedirs(logs_dir_path, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        log_filename = logs_dir_path / f"riven-{timestamp}.log"

        handlers.append(
            {
                "sink": log_filename,
                "level": level.upper(),
                "format": log_format,
                "rotation": rotation_value,
                "retention": retention_value,
                "compression": (
                    compression_value if compression_value != "disabled" else None
                ),
                "backtrace": False,
                "diagnose": True,
                "enqueue": True,
            }
        )

    logger.configure(handlers=handlers)


def log_cleaner():
    """Remove old log files based on user retention settings, leaving the most recent one."""
    log_settings = settings_manager.settings.logging
    if not log_settings.enabled:
        return

    global LAST_LOGS_CLEANED
    if (
        LAST_LOGS_CLEANED
        and (datetime.now() - LAST_LOGS_CLEANED).total_seconds() < 3600
    ):
        return

    try:
        logs_dir_path = data_dir_path / "logs"
        if not logs_dir_path.exists():
            return

        # Include compressed rotated files too (e.g., .log.gz/.zip)
        log_files = sorted(
            logs_dir_path.glob("riven-*.log*"), key=lambda x: x.stat().st_mtime
        )
        cleaned = False
        retention_hours = max(0, int(log_settings.retention_hours))

        for log_file in log_files[:-1]:
            # remove files older than the configured retention window
            file_age_hours = (
                datetime.now() - datetime.fromtimestamp(log_file.stat().st_mtime)
            ).total_seconds() / 3600
            if file_age_hours > retention_hours:
                log_file.unlink()
                cleaned = True

        if cleaned:
            LAST_LOGS_CLEANED = datetime.now()
            logger.debug(f"Cleaned up old logs older than {retention_hours} hours.")
    except Exception as e:
        logger.error(f"Failed to clean old logs: {e}")


setup_logger(settings_manager.settings.log_level)
