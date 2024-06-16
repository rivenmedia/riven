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

    # Core
    logger.level("PROGRAM", no=36, color="<blue>", icon="🤖")
    logger.level("DEBRID", no=38, color="<yellow>", icon="🔗")
    logger.level("SYMLINKER", no=39, color="<fg 249,231,159>", icon="🔗")
    logger.level("SCRAPER", no=40, color="<magenta>", icon="👻")
    logger.level("COMPLETED", no=41, color="<white>", icon="🟢")
    logger.level("CACHE", no=42, color="<green>", icon="📜")
    logger.level("NOT_FOUND", no=43, color="<fg 129,133,137>", icon="🤷‍")
    logger.level("NEW", no=44, color="<fg #e63946>", icon="✨")
    logger.level("FILES", no=45, color="<light-yellow>", icon="🗃️ ")
    logger.level("ITEM", no=46, color="<fg #92a1cf>", icon="🗃️ ")
    logger.level("DISCOVERY", no=47, color="<fg #e56c49>", icon="🔍")

    # API Logging
    logger.level("API", no=47, color="<fg #006989>", icon="👾")

    # Extras
    logger.level("PLEX", no=47, color="<fg #DAD3BE>", icon="📽️ ")
    logger.level("TRAKT", no=48, color="<fg #1DB954>", icon="🎵")

    # Default
    logger.level("INFO", icon="📰")
    logger.level("DEBUG", icon="🤖")
    logger.level("WARNING", icon="⚠️ ")
    logger.level("CRITICAL", icon="")

    # Log format to match the old log format, but with color
    log_format = (
        "<red>{time:YYYY-MM-DD}</red> <red>{time:HH:mm:ss}</red> | "
        "<level>{level.icon}</level> <level>{level: <9}</level> | "
        "<cyan>{module}</cyan>.<cyan>{function}</cyan> - <level>{message}</level>"
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