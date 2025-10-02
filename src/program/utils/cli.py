import argparse
import os
import subprocess
from pathlib import Path
from datetime import datetime

from program.db.db_functions import (
    hard_reset_database,
)
from program.utils.logging import log_cleaner, logger


def snapshot_database(snapshot_dir: Path = None):
    """
    Create a timestamped SQL dump of the configured PostgreSQL database and update a `latest.sql` symlink.
    
    Creates a snapshot file in `snapshot_dir` (defaults to ./data/db_snapshot), choosing either to run `pg_dump` directly or to run it inside a detected PostgreSQL Docker container when the configured host indicates a local/container instance. On success the snapshot file is written and `latest.sql` is updated to point to the new snapshot; on failure no symlink update is performed.
    
    Parameters:
        snapshot_dir (Path | None): Directory to store snapshot files. If None, uses ./data/db_snapshot.
    
    Returns:
        bool: `True` if the snapshot was created and the `latest.sql` symlink updated, `False` otherwise.
    """
    from program.settings.manager import settings_manager

    if snapshot_dir is None:
        snapshot_dir = Path("./data/db_snapshot")

    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Parse database connection string
    db_url = settings_manager.settings.database.host
    # Format: postgresql+psycopg2://user:password@host:port/dbname

    try:
        # Extract connection details
        if "://" in db_url:
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
        else:
            logger.error("Invalid database URL format")
            return False

        # Create snapshot filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_file = snapshot_dir / f"riven_snapshot_{timestamp}.sql"

        # Check if we're running in Docker or need to use docker exec
        # If host is localhost/127.0.0.1, try to use docker exec to access postgres container
        use_docker = host in ["localhost", "127.0.0.1", "riven-db", "postgres"]

        if use_docker:
            # Try to find postgres container
            container_name = None
            for name in ["postgres", "riven-db", "riven_postgres"]:
                check_cmd = ["docker", "inspect", name]
                check_result = subprocess.run(check_cmd, capture_output=True, text=True)
                if check_result.returncode == 0:
                    container_name = name
                    break

            if container_name:
                # Use docker exec to run pg_dump inside the container
                # Pass PGPASSWORD into the container via -e flag
                cmd = [
                    "docker", "exec",
                    "-e", f"PGPASSWORD={password}",
                    container_name,
                    "pg_dump",
                    "-U", user,
                    "-d", dbname,
                    "--clean",
                    "--if-exists",
                ]

                logger.info(f"Creating database snapshot at {snapshot_file} using docker exec...")
                # Use os.environ.copy() to preserve PATH and other env vars
                env = os.environ.copy()
                # Don't set PGPASSWORD in local env since we pass it via docker exec -e
                result = subprocess.run(cmd, env=env, capture_output=True, text=True)

                if result.returncode == 0:
                    # Write output to file
                    snapshot_file.write_text(result.stdout)
                else:
                    logger.error(f"Failed to create snapshot: {result.stderr}")
                    return False
            else:
                logger.error("Could not find postgres container. Available containers: postgres, riven-db, riven_postgres")
                return False
        else:
            # Use pg_dump directly (assumes it's in PATH)
            # Preserve PATH and other env vars by copying os.environ
            env = os.environ.copy()
            if password:
                env["PGPASSWORD"] = password
            else:
                env.pop("PGPASSWORD", None)

            cmd = [
                "pg_dump",
                "-h", host,
                "-p", port,
                "-U", user,
                "-d", dbname,
                "-f", str(snapshot_file),
                "--clean",
                "--if-exists",
            ]

            logger.info(f"Creating database snapshot at {snapshot_file}...")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)

            if result.returncode == 0:
                logger.success(f"Database snapshot created successfully: {snapshot_file}")
                # Create a symlink to latest snapshot
                latest_link = snapshot_dir / "latest.sql"
                if latest_link.exists() or latest_link.is_symlink():
                    latest_link.unlink()
                latest_link.symlink_to(snapshot_file.name)
                logger.info(f"Latest snapshot link updated: {latest_link}")
                return True
            else:
                logger.error(f"Failed to create snapshot: {result.stderr}")
                return False

        # Common success path for docker exec (already handled above)
        logger.success(f"Database snapshot created successfully: {snapshot_file}")
        latest_link = snapshot_dir / "latest.sql"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(snapshot_file.name)
        logger.info(f"Latest snapshot link updated: {latest_link}")
        return True

    except Exception as e:
        logger.error(f"Error creating database snapshot: {e}")
        return False


def restore_database(snapshot_file: Path = None):
    """
    Restore the configured PostgreSQL database from a SQL snapshot file.
    
    Parameters:
        snapshot_file (Path | None): Path to the SQL snapshot to restore. If None, uses ./data/db_snapshot/latest.sql.
    
    Returns:
        bool: `True` if the restore completed successfully, `False` otherwise.
    """
    from program.settings.manager import settings_manager

    if snapshot_file is None:
        snapshot_dir = Path("./data/db_snapshot")
        snapshot_file = snapshot_dir / "latest.sql"

    if not snapshot_file.exists():
        logger.error(f"Snapshot file not found: {snapshot_file}")
        return False

    # Parse database connection string
    db_url = settings_manager.settings.database.host

    try:
        # Extract connection details (same as snapshot_database)
        if "://" in db_url:
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

            if ":" in host_part:
                host, port = host_part.split(":", 1)
            else:
                host = host_part
                port = "5432"
        else:
            logger.error("Invalid database URL format")
            return False

        # Check if we're running in Docker or need to use docker exec
        use_docker = host in ["localhost", "127.0.0.1", "riven-db", "postgres"]

        if use_docker:
            # Try to find postgres container
            container_name = None
            for name in ["postgres", "riven-db", "riven_postgres"]:
                check_cmd = ["docker", "inspect", name]
                check_result = subprocess.run(check_cmd, capture_output=True, text=True)
                if check_result.returncode == 0:
                    container_name = name
                    break

            if container_name:
                # Use docker exec to run psql inside the container
                logger.info(f"Restoring database from {snapshot_file} using docker exec...")

                # Read snapshot file and pipe to psql
                with open(snapshot_file, "r") as f:
                    snapshot_content = f.read()

                # Pass PGPASSWORD into the container via -e flag
                cmd = [
                    "docker", "exec", "-i",
                    "-e", f"PGPASSWORD={password}",
                    container_name,
                    "psql",
                    "-U", user,
                    "-d", dbname,
                ]

                # Use os.environ.copy() to preserve PATH and other env vars
                env = os.environ.copy()
                # Don't set PGPASSWORD in local env since we pass it via docker exec -e
                result = subprocess.run(cmd, env=env, input=snapshot_content, capture_output=True, text=True)

                if result.returncode == 0:
                    logger.success(f"Database restored successfully from {snapshot_file}")
                    return True
                else:
                    logger.error(f"Failed to restore database: {result.stderr}")
                    return False
            else:
                logger.error("Could not find postgres container. Available containers: postgres, riven-db, riven_postgres")
                return False
        else:
            # Use psql directly (assumes it's in PATH)
            # Preserve PATH and other env vars by copying os.environ
            env = os.environ.copy()
            if password:
                env["PGPASSWORD"] = password
            else:
                env.pop("PGPASSWORD", None)

            cmd = [
                "psql",
                "-h", host,
                "-p", port,
                "-U", user,
                "-d", dbname,
                "-f", str(snapshot_file),
            ]

            logger.info(f"Restoring database from {snapshot_file}...")
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)

            if result.returncode == 0:
                logger.success(f"Database restored successfully from {snapshot_file}")
                return True
            else:
                logger.error(f"Failed to restore database: {result.stderr}")
                return False

    except Exception as e:
        logger.error(f"Error restoring database: {e}")
        return False


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
        action="store_true",
        help="Create a snapshot of the current database state.",
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
        "-p", "--port",
        type=int,
        default=8080,
        help="Port to run the server on (default: 8080)"
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
        success = snapshot_database()
        exit(0 if success else 1)

    if args.restore_db:
        if args.restore_db == "latest":
            snapshot_file = Path("./data/db_snapshot/latest.sql")
        else:
            snapshot_file = Path(args.restore_db)
        success = restore_database(snapshot_file)
        exit(0 if success else 1)

    return args
