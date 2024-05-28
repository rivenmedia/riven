"""Logging utils"""

import os
import sys
from datetime import datetime

from loguru import logger
from program.settings.manager import settings_manager
from utils import data_dir_path

from rich.console import Console
from rich.table import Table


class FileLogger:
    """A logger for rich tables."""

    def __init__(self, title, show_header=False, header_style=None):
        self.title = title
        self.show_header = show_header
        self.header_style = header_style
        self.create_new_table()

    def create_new_table(self):
        """Create a new table with the initial configuration."""
        self.table = Table(title=self.title, show_header=False, header_style=self.header_style or "bold magenta")

    def add_column(self, column_name, style=None):
        """Add a column to the table."""
        self.table.add_column(column_name, style=style)
    
    def add_row(self, *args):
        """Add a row to the table."""
        self.table.add_row(*args)
    
    def log_table(self):
        """Log the table to the console."""
        console.print(self.table)
        self.clear_table()

    def clear_table(self):
        """Clear the table by reinitializing it."""
        self.create_new_table()

    def progress_bar(self, *args):
        """Add a progress bar to the table."""
        self.table.add_row(*args)


def setup_logger(level):
    """Setup the logger"""
    logs_dir_path = data_dir_path / "logs"
    os.makedirs(logs_dir_path, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    log_filename = logs_dir_path / f"iceberg-{timestamp}.log"

    logger.level("PROGRAM", no=36, color="<blue>", icon="🤖")
    logger.level("DEBRID", no=38, color="<yellow>", icon="🔗")
    logger.level("SYMLINKER", no=39, color="<fg 249,231,159>", icon="🔗")
    logger.level("SCRAPER", no=40, color="<magenta>", icon="👻")
    logger.level("COMPLETED", no=41, color="<green>", icon="🟢")
    logger.level("CACHE", no=42, color="<green>", icon="📜")
    logger.level("NOT_FOUND", no=43, color="<fg 129,133,137>", icon="🤷‍")
    logger.level("NEW", no=44, color="<fg #e63946>", icon="✨")
    logger.level("FILES", no=45, color="<yellow>", icon="🗃️")

    # set the default info and debug level icons
    logger.level("INFO", icon="📰")
    logger.level("DEBUG", icon="🤖")
    logger.level("WARNING", icon="⚠️ ")

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
            "buffer_size": 1024 * 1024
        },
        {
            "sink": log_filename, 
            "level": level, 
            "format": log_format, 
            "rotation": "2 hours", 
            "retention": "1 days", 
            "compression": "zip", 
            "backtrace": False, 
            "diagnose": True,
            "enqueue": True,
            "buffer_size": 1024 * 1024
        },
    ])


def clean_old_logs():
    """Remove old log files based on retention settings."""
    try:
        logs_dir_path = data_dir_path / "logs"
        for log_file in logs_dir_path.glob("iceberg-*.log"):
            # remove files older than 2 hours
            if (datetime.now() - datetime.fromtimestamp(log_file.stat().st_mtime)).total_seconds() / 3600 > 2:
                log_file.unlink()
                logger.log("COMPLETED", f"Old log file {log_file.name} removed.")
    except Exception as e:
        logger.log("ERROR", f"Failed to clean old logs: {e}")


console = Console()
table = FileLogger("Downloaded Files")

log_level = "DEBUG" if settings_manager.settings.debug else "INFO"
setup_logger(log_level)
