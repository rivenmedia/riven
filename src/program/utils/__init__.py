import os
import re
import secrets
import string

from collections.abc import Callable, Iterator
from contextlib import contextmanager
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
    sig_figs: int = 3,
) -> Iterator[None]:
    """Context manager for benchmarking code execution time."""

    try:
        start_time = time()

        yield
    finally:
        end_time = time()

        if log:
            log(float(f"{end_time - start_time:.{sig_figs}f}"))
        else:
            logger.debug(
                f"Execution time: {end_time - start_time:.{sig_figs}f} seconds"
            )
