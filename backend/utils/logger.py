"""Logging utils"""

import logging
import os
import sys
from datetime import datetime

from loguru import logger
from program.settings.manager import settings_manager
from rich.console import Console
from utils import data_dir_path


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
        "DEBRID": (38, "cc3333", "🔗"),
        "SYMLINKER": (39, "F9E79F", "🔗"),
        "SCRAPER": (40, "D299EA", "👻"),
        "COMPLETED": (41, "FFFFFF", "🟢"),
        "CACHE": (42, "527826", "📜"),
        "NOT_FOUND": (43, "818589", "🤷‍"),
        "NEW": (44, "e63946", "✨"),
        "FILES": (45, "FFFFE0", "🗃️ "),
        "ITEM": (46, "92a1cf", "🗃️ "),
        "DISCOVERY": (47, "e56c49", "🔍"),
        "API": (47, "006989", "👾"),
        "PLEX": (47, "DAD3BE", "📽️ "),
        "LOCAL": (48, "DAD3BE", "📽️ "),
        "JELLYFIN": (48, "DAD3BE", "📽️ "),
        "EMBY": (48, "DAD3BE", "📽️ "),
        "TRAKT": (48, "1DB954", "🎵"),
    }

    # Set log levels
    for name, (no, default_color, default_icon) in log_levels.items():
        color, icon = get_log_settings(name, default_color, default_icon)
        logger.level(name, no=no, color=color, icon=icon)

    # Default log levels
    logger.level("INFO", icon="📰")
    logger.level("DEBUG", icon="🤖")
    logger.level("WARNING", icon="⚠️ ")
    logger.level("CRITICAL", icon="")
    logger.level("SUCCESS", icon="✔️ ")

    # Log format to match the old log format, but with color
    log_format = (
        "<fg #818589>{time:YY-MM-DD} {time:HH:mm:ss}</fg #818589> | "
        "<level>{level.icon}</level> <level>{level: <9}</level> | "
        "<fg #990066>{module}</fg #990066>.<fg #990066>{function}</fg #990066> - <level>{message}</level>"
    )

    logger.configure(handlers=[
        {
            "sink": sys.stderr,
            "level": "DEBUG",
            "format": log_format,
            "backtrace": False,
            "diagnose": False,
            "enqueue": True,
        },
        {
            "sink": log_filename, 
            "level": level, 
            "format": log_format, 
            "rotation": "50 MB", 
            "retention": "8 hours", 
            "compression": None, 
            "backtrace": False, 
            "diagnose": True,
            "enqueue": True,
        }
    ])


def scrub_logs():
    """Remove old log files based on retention settings."""
    try:
        logs_dir_path = data_dir_path / "logs"
        for log_file in logs_dir_path.glob("riven-*.log"):
            # remove files older than 8 hours
            if (datetime.now() - datetime.fromtimestamp(log_file.stat().st_mtime)).total_seconds() / 3600 > 8:
                log_file.unlink()
                logger.log("COMPLETED", f"Old log file {log_file.name} removed.")
    except Exception as e:
        logger.log("ERROR", f"Failed to clean old logs: {e}")


console = Console()
log_level = "DEBUG" if settings_manager.settings.debug else "INFO"
setup_logger(log_level)