import time
from multiprocessing import Lock

from requests import RequestException


class RateLimitExceeded(RequestException):
    pass


class RateLimiter:
    def __init__(self, max_calls, period, raise_on_limit=False):
        self.max_calls = max_calls
        self.period = period
        self.tokens = max_calls
        self.last_call = time.time() - period
        self.lock = Lock()
        self.raise_on_limit = raise_on_limit

    def limit_hit(self):
        self.tokens = 0

    def __enter__(self):
        with self.lock:
            current_time = time.time()
            time_elapsed = current_time - self.last_call

            if time_elapsed >= self.period:
                self.tokens = self.max_calls

            if self.tokens <= 0:
                if self.raise_on_limit:
                    raise RateLimitExceeded("Rate limit exceeded")
                time.sleep(self.period - time_elapsed)
                self.last_call = time.time()
                self.tokens = self.max_calls
            else:
                self.tokens -= 1

            self.last_call = current_time
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass