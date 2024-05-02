"""Logging utils"""

import datetime
import logging
import os
import re

from utils import data_dir_path


class RedactSensitiveInfo(logging.Filter):
    """logging filter to redact sensitive info"""

    def __init__(self):
        super().__init__("redact_sensitive_info")
        self.patterns = {
            "api_key": re.compile(r"(\'api_key\'\s*:\s*\')[^\']*\'", re.IGNORECASE),
            "token": re.compile(r"(\'token\'\s*:\s*\')[^\']*\'", re.IGNORECASE),
            "user": re.compile(r"(\'user\'\s*:\s*\')[^\']*\'", re.IGNORECASE),
            "watchlist": re.compile(r"(\'watchlist\'\s*:\s*\')[^\']*\'", re.IGNORECASE),
        }

    def _redact_string(self, data):
        if isinstance(data, str):
            for key, pattern in self.patterns.items():
                data = pattern.sub(f"'{key}' : 'REDACTED'", data)
        return data

    def _redact_nested(self, data):
        if isinstance(data, dict):
            redacted_dict = {}
            for key, value in data.items():
                for key2, _ in self.patterns.items():
                    if key in key2:
                        redacted_dict[key] = "REDACTED"
                        break
                    redacted_dict[key] = value
            return redacted_dict
        if isinstance(data, list):
            return [self._redact_nested(item) for item in data]
        if isinstance(data, tuple):
            if len(data) > 0 and isinstance(data[0], str):
                return (self._redact_string(data[0]),) + tuple(
                    self._redact_nested(item) for item in data[1:]
                )
            return tuple(self._redact_nested(item) for item in data)
        if isinstance(data, str):
            return self._redact_string(data)
        return data

    def filter(self, record):
        if record.args and isinstance(record.args, tuple):
            record.args = self._redact_nested(record.args)
        return True


class Logger(logging.Logger):
    """Logging class"""

    def __init__(self):
        self.timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        self.filename = f"iceberg-{self.timestamp}.log"
        super().__init__(self.filename)
        self.formatter = logging.Formatter(
            "[%(asctime)s | %(levelname)s] <%(module)s.%(funcName)s> - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.logs_dir_path = data_dir_path / "logs"
        os.makedirs(self.logs_dir_path, exist_ok=True)

        # self.addFilter(RedactSensitiveInfo())

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(self.formatter)
        self.addHandler(console_handler)
        self.console_handler = console_handler
        self.file_handler = None

    def configure_logger(self, debug=False, log=False):
        log_level = logging.DEBUG if debug else logging.INFO
        self.setLevel(log_level)

        # Update console handler level
        for handler in self.handlers:
            handler.setLevel(log_level)

        # Configure file handler
        if log and not self.file_handler:
            # Only add a new file handler if it hasn't been added before
            file_handler = logging.FileHandler(
                self.logs_dir_path / self.filename, encoding="utf-8"
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(self.formatter)
            self.addHandler(file_handler)
            self.file_handler = (
                file_handler  # Keep a reference to avoid adding it again
            )
        elif not log and self.file_handler:
            # If logging to file is disabled but the handler exists, remove it
            self.removeHandler(self.file_handler)
            self.file_handler = None


logger = Logger()
