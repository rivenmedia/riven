import argparse
import os
import subprocess
from pathlib import Path
from datetime import datetime

from program.db.db_functions import (
    hard_reset_database,
)
from program.utils.logging import log_cleaner, logger
import contextlib


def _parse_db_connection(db_url: str) -> tuple[str, str, str, str, str] | None:
    """
    Parse database connection string.

    Returns:
        Tuple of (user, password, host, port, dbname) or None if invalid
    """

    # Format: postgresql+psycopg2://user:password@host:port/dbname
    try:
        if "://" not in db_url:
            logger.error("Invalid database URL format")
            return None

        _, rest = db_url.split("://", 1)
        if "@" in rest:
            credentials, host_db = rest.split("@", 1)
            if ":" in credentials:
                user, password = credentials.split(":", 1)
            else:
                user = credentials
                password = ""
        else:
            user = "postgres"
            password = ""
            host_db = rest

        if "/" in host_db:
            host_part, dbname = host_db.rsplit("/", 1)
        else:
            host_part = host_db
            dbname = "riven"

        # Extract host and port
        if ":" in host_part:
            host, port = host_part.split(":", 1)
        else:
            host = host_part
            port = "5432"

        logger.debug(
            f"Parsed DB connection - host: {host}, port: {port}, user: {user}, dbname: {dbname}"
        )
        return user, password, host, port, dbname
    except Exception as e:
        logger.error(f"Error parsing database URL: {e}")
        return None


def _setup_pg_env(password: str) -> dict[str, str]:
    """Setup environment variables for PostgreSQL commands."""

    env = os.environ.copy()

    if password:
        env["PGPASSWORD"] = password
    else:
        env.pop("PGPASSWORD", None)

    return env


def _run_pg_dump(
    host: str, port: str, user: str, password: str, dbname: str, output_file: Path
) -> bool:
    """
    Run pg_dump directly (not via docker exec).

    Returns:
        True if successful, False otherwise
    """
    cmd = [
        "pg_dump",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        dbname,
        "-f",
        str(output_file),
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
    ]

    logger.info(f"Creating database snapshot at {output_file} using pg_dump...")
    env = _setup_pg_env(password)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode == 0:
        return True
    else:
        # Check if pg_dump is not installed
        if "No such file or directory" in result.stderr or result.returncode == 127:
            logger.error("pg_dump not found. Please install postgresql17 binaries.")
        else:
            logger.error(f"Failed to create snapshot: {result.stderr}")
        return False


def _run_psql(
    host: str, port: str, user: str, password: str, dbname: str, snapshot_file: Path
) -> bool:
    """
    Run psql directly (not via docker exec).

    Returns:
        True if successful, False otherwise
    """
    cmd = [
        "psql",
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        dbname,
        "-f",
        str(snapshot_file),
    ]

    logger.info(f"Restoring database from {snapshot_file} using psql...")
    env = _setup_pg_env(password)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)

    if result.returncode == 0:
        return True
    else:
        # Check if psql is not installed
        if "No such file or directory" in result.stderr or result.returncode == 127:
            logger.error("pg_dump not found. Please install postgresql17 binaries.")
        else:
            logger.error(f"Failed to restore database: {result.stderr}")
        return False


def snapshot_database(
    snapshot_dir: Path | None = None,
    snapshot_name: str | None = None,
) -> str | None:
    """
    Create a timestamped SQL dump of the configured PostgreSQL database and update a `latest.sql` symlink.

    Uses `pg_dump` directly to create a snapshot. Requires `postgresql-client` to be installed on the system.
    On success the snapshot file is written and `latest.sql` is updated to point to the new snapshot; on failure no symlink update is performed.

    Parameters:
        snapshot_dir (Path | None): Directory to store snapshot files. If None, uses ./data/db_snapshot.
        snapshot_name (str | None): Custom name for the snapshot file. If None, uses timestamped name.

    Returns:
        str | None: The snapshot filename if successful, None otherwise.
    """
    from program.settings import settings_manager

    if snapshot_dir is None:
        snapshot_dir = Path("./data/db_snapshot")

    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Parse database connection string
    db_url = str(settings_manager.settings.database.host)

    try:
        # Parse connection details
        parsed = _parse_db_connection(db_url)
        if not parsed:
            return None
        user, password, host, port, dbname = parsed

        # Create snapshot filename
        if snapshot_name:
            # Use custom name (ensure it ends with .sql)
            if not snapshot_name.endswith(".sql"):
                snapshot_name = f"{snapshot_name}.sql"
            snapshot_file = snapshot_dir / snapshot_name
        else:
            # Use timestamped name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_file = snapshot_dir / f"riven_snapshot_{timestamp}.sql"

        success = _run_pg_dump(host, port, user, password, dbname, snapshot_file)

        if success:
            logger.success(f"Database snapshot created successfully: {snapshot_file}")
            # Create a symlink to latest snapshot
            latest_link = snapshot_dir / "latest.sql"
            if latest_link.exists() or latest_link.is_symlink():
                latest_link.unlink()
            latest_link.symlink_to(snapshot_file.name)
            logger.info(f"Latest snapshot link updated: {latest_link}")
            return snapshot_file.name
        else:
            return None

    except Exception as e:
        logger.error(f"Error creating database snapshot: {e}")
        return None


def restore_database(snapshot_file: Path | None = None):
    """
    Restore the configured PostgreSQL database from a SQL snapshot file.

    Uses `psql` directly to restore the database. Requires `postgresql-client` to be installed on the system.

    Parameters:
        snapshot_file (Path | None): Path to the SQL snapshot to restore. If None, uses ./data/db_snapshot/latest.sql.

    Returns:
        bool: `True` if the restore completed successfully, `False` otherwise.
    """
    from program.settings import settings_manager

    if snapshot_file is None:
        snapshot_dir = Path("./data/db_snapshot")
        snapshot_file = snapshot_dir / "latest.sql"

    if not snapshot_file.exists():
        logger.error(f"Snapshot file not found: {snapshot_file}")
        return False

    # Parse database connection string
    db_url = str(settings_manager.settings.database.host)

    try:
        # Parse connection details
        parsed = _parse_db_connection(db_url)
        if not parsed:
            return False
        user, password, host, port, dbname = parsed

        success = _run_psql(host, port, user, password, dbname, snapshot_file)

        if success:
            logger.success(f"Database restored successfully from {snapshot_file}")
            return True
        else:
            return False

    except Exception as e:
        logger.error(f"Error restoring database: {e}")
        return False


def clean_snapshots(snapshot_name: str | None = None) -> tuple[bool, list[str]]:
    """
    Clean database snapshot files.

    Parameters:
        snapshot_name (str | None): Specific snapshot file to delete. If None, deletes all snapshots.

    Returns:
        tuple[bool, list[str]]: (success, list of deleted filenames)
    """
    snapshot_dir = Path("./data/db_snapshot")

    if not snapshot_dir.exists():
        logger.info("No snapshot directory found, nothing to clean")
        return True, []

    deleted_files: list[str] = []

    try:
        if snapshot_name:
            if "/" in snapshot_name or "\\" in snapshot_name or ".." in snapshot_name:
                logger.error(f"Invalid snapshot name: {snapshot_name}")
                return False, []

            if not snapshot_name.endswith(".sql"):
                snapshot_name = f"{snapshot_name}.sql"

            snapshot_file = snapshot_dir / snapshot_name

            if not snapshot_file.exists():
                logger.error(f"Snapshot file not found: {snapshot_name}")
                return False, []

            # Check if latest.sql points to a file that is being deleted
            latest_link = snapshot_dir / "latest.sql"
            symlink_points_to_deleted = False
            if latest_link.is_symlink():
                with contextlib.suppress(Exception):
                    symlink_points_to_deleted = (
                        latest_link.resolve().name == snapshot_name
                    )

            snapshot_file.unlink()
            deleted_files.append(snapshot_name)
            logger.success(f"Deleted snapshot: {snapshot_name}")

            if symlink_points_to_deleted:
                latest_link.unlink()
                logger.info("Removed latest.sql symlink (pointed to deleted file)")
        else:
            for snapshot_file in snapshot_dir.glob("*.sql"):
                if snapshot_file.is_symlink():
                    snapshot_file.unlink()
                    deleted_files.append(f"{snapshot_file.name} (symlink)")
                elif snapshot_file.is_file():
                    snapshot_file.unlink()
                    deleted_files.append(snapshot_file.name)

            logger.success(f"Deleted {len(deleted_files)} snapshot(s)")

        return True, deleted_files

    except Exception as e:
        logger.error(f"Error cleaning snapshots: {e}")
        return False, deleted_files


def handle_args():
    """
    Parse CLI arguments for database utilities and perform immediate actions for certain flags.

    When invoked, parses flags for cache ignoring, hard database reset, log cleaning, creating a database snapshot, restoring a snapshot, and server port. If --hard_reset_db or --clean_logs are set, the corresponding operation is performed and the process exits. If --snapshot_db or --restore_db are set, the snapshot or restore operation is performed and the process exits with status 0 on success or 1 on failure. Otherwise, the parsed arguments are returned for further use.

    Returns:
        argparse.Namespace: The parsed command-line arguments.
    """
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
        "--snapshot_db",
        type=str,
        metavar="SNAPSHOT_FILE",
        nargs="?",
        const=True,
        help="Create a snapshot of the current database state. Optionally specify a custom filename.",
    )
    parser.add_argument(
        "--restore_db",
        type=str,
        metavar="SNAPSHOT_FILE",
        nargs="?",
        const="latest",
        help="Restore database from a snapshot file (default: latest snapshot).",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=8080,
        help="Port to run the server on (default: 8080)",
    )
    parser.add_argument(
        "--clean_snapshots",
        type=str,
        metavar="SNAPSHOT_FILE",
        nargs="?",
        const=True,
        help="Clean database snapshots. If no filename provided, deletes all snapshots.",
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

    if args.snapshot_db:
        snapshot_name = args.snapshot_db if isinstance(args.snapshot_db, str) else None
        success = snapshot_database(snapshot_name=snapshot_name)
        exit(0 if success else 1)

    if args.restore_db:
        if args.restore_db == "latest":
            snapshot_file = Path("./data/db_snapshot/latest.sql")
        else:
            snapshot_file = Path(args.restore_db)
        success = restore_database(snapshot_file)
        exit(0 if success else 1)

    if args.clean_snapshots:
        snapshot_name = (
            args.clean_snapshots if isinstance(args.clean_snapshots, str) else None
        )
        success, deleted = clean_snapshots(snapshot_name)
        if deleted:
            logger.info(f"Deleted files: {', '.join(deleted)}")
        exit(0 if success else 1)

    return args
