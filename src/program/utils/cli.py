import argparse

from program.db.db_functions import (
    hard_reset_database,
)
from program.utils.logging import log_cleaner, logger


def handle_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ignore_cache",
        action="store_true",
        help="Ignore the cached metadata, create new data from scratch.",
    )
    parser.add_argument(
        "--hard_reset_db",
        action="store_true",
        help="Hard reset the database.",
    )
    parser.add_argument(
        "--clean_logs",
        action="store_true",
        help="Clean old logs.",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=8080,
        help="Port to run the server on (default: 8000)"
    )

    args = parser.parse_args()

    if args.hard_reset_db:
        hard_reset_database()
        logger.info("Hard reset the database")
        exit(0)

    if args.clean_logs:
        log_cleaner()
        logger.info("Cleaned old logs.")
        exit(0)

    return args
