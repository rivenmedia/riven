import argparse

from program.db.db_functions import (
    hard_reset_database,
    hard_reset_database_pre_migration,
)
from program.services.libraries.symlink import fix_broken_symlinks
from program.settings.manager import settings_manager
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
        "--hard_reset_db_pre_migration",
        action="store_true",
        help="Hard reset the database.",
    )
    parser.add_argument(
        "--clean_logs",
        action="store_true",
        help="Clean old logs.",
    )
    parser.add_argument(
        "--fix_symlinks",
        action="store_true",
        help="Fix broken symlinks.",
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

    if args.hard_reset_db_pre_migration:
        hard_reset_database_pre_migration()
        logger.info("Hard reset the database")
        exit(0)

    if args.clean_logs:
        log_cleaner()
        logger.info("Cleaned old logs.")
        exit(0)

    if args.fix_symlinks:
        fix_broken_symlinks(settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path)
        exit(0)

    return args
