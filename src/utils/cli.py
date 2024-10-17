import argparse

from program.db.db_functions import hard_reset_database, resolve_duplicates
from program.libraries.symlink import fix_broken_symlinks
from program.settings.manager import settings_manager
from utils.logger import log_cleaner, logger


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
        "--fix_symlinks",
        action="store_true",
        help="Fix broken symlinks.",
    )
    parser.add_argument(
        "--plex_listener",
        action="store_true",
        help="Start a Plex listener.",
    )
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=8080,
        help='Port to run the server on (default: 8000)'
    )
    parser.add_argument(
        "--resolve_duplicates",
        action="store_true",
        help="Resolve duplicate items.",
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

    if args.fix_symlinks:
        fix_broken_symlinks(settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path)
        exit(0)

    if args.resolve_duplicates:
        resolve_duplicates()
        exit(0)

    if args.plex_listener:
        plex_listener()
        exit(0)

    return args


def plex_listener():
    """Start a Plex listener."""
    # NOTE: This isn't staying, just merely testing
    import time

    from plexapi.server import PlexServer

    def plex_event(event):
        logger.debug(f"Event: {event}")

    try:
        settings = settings_manager.settings.updaters.plex
        plex = PlexServer(settings.url, settings.token)
        plex.startAlertListener(plex_event)

        logger.debug("Started Plex listener")
        logger.debug("Press Ctrl+C to stop")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        exit(0)