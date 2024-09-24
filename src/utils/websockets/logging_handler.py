import logging

from utils.websockets import manager


class Handler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            message = self.format(record)
            manager.send_log_message(message)
        except Exception:
            self.handleError(record)