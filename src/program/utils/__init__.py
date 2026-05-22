import os
import re
import secrets
import string

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from time import time
from loguru import logger
from pathlib import Path

root_dir = Path(__file__).resolve().parents[3]

data_dir_path = root_dir / "data"
alembic_dir = data_dir_path / "alembic"


def get_version() -> str:
    with open(root_dir / "pyproject.toml") as file:
        pyproject_toml = file.read()

    match = re.search(r'version = "(.+)"', pyproject_toml)
    if match:
        version = match.group(1)
    else:
        raise ValueError("Could not find version in pyproject.toml")
    return version


def naive_local_datetime(dt: datetime | None) -> datetime | None:
    """
    Coerce aware datetimes to naive local wall time for use with datetime.now().

    Use before comparing or subtracting any DB timestamp, UTC API timestamp, or
    queue run_at against naive datetimes — mixing aware and naive raises TypeError.
    """

    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone().replace(tzinfo=None)


def format_api_datetime(dt: datetime | None) -> str | None:
    """
    Serialize a datetime for API/JSON consumers.

    Naive datetimes are treated as UTC (Riven runs on UTC wall clock). Always
    emits a trailing Z so browsers parse consistently.
    """

    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def generate_api_key():
    """Generate a secure API key of the specified length."""
    API_KEY = os.getenv("API_KEY", "")
    if len(API_KEY) != 32:
        logger.warning("env.API_KEY is not 32 characters long, generating a new one...")
        characters = string.ascii_letters + string.digits

        # Generate the API key
        api_key = "".join(secrets.choice(characters) for _ in range(32))
        logger.warning(f"New api key: {api_key}")
    else:
        api_key = API_KEY

    return api_key


@contextmanager
def benchmark(
    *,
    log: Callable[[float], None] | None,
    decimal_places: int = 3,
) -> Iterator[None]:
    """Context manager for benchmarking code execution time."""

    start_time = time()

    try:
        yield
    finally:
        end_time = time()
        elapsed = end_time - start_time

        if log:
            log(round(elapsed, decimal_places))
        else:
            logger.debug(f"Execution time: {elapsed:.{decimal_places}f} seconds")
