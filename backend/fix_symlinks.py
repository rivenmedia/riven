import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import structlog
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = structlog.get_logger()


def check_dead_symlinks(base_path):
    """
    Traverse through the directory and log any symlinks that point to non-existent targets.

    :param base_path: Path where the symlinks are located (e.g., "/mnt/library/shows").
    """
    count = 0
    dead_symlink_count = 0
    logger.info("Checking for dead symlinks in the symlink directory", symlink_path=base_path)

    for root, dirs, files in os.walk(base_path):
        for name in files + dirs:
            path = os.path.join(root, name)
            if os.path.islink(path):
                target_path = os.readlink(path)
                if not os.path.exists(os.path.join(os.path.dirname(path), target_path)):
                    logger.warning("Dead symbolic link found", symlink=path, target=target_path)
                    dead_symlink_count += 1
                count += 1

    logger.info("Symlink check completed", total_checked=count, dead_links_found=dead_symlink_count)


def fix_symlinks(base_path, incorrect_target_base, correct_target_base):
    """
    Traverse through the symlink directory and correct symlinks by replacing the incorrect target base with the correct target base,
    and validate if the corrected target files exist.

    :param base_path: Path where the symlinks are located (e.g., "/mnt/library/shows").
    :param incorrect_target_base: The incorrect part of the target path that needs correction (e.g., "/mnt/zurg").
    :param correct_target_base: The correct target path to replace the incorrect part (e.g., "/mnt/zurg/__all__").
    """
    count = 0
    fixed_count = 0
    missing_files = []
    logger.info("Starting to fix symlinks")

    for root, _, files in os.walk(base_path):
        for filename in files:
            symlink_path = os.path.join(root, filename)
            if os.path.islink(symlink_path):
                target_path = os.readlink(symlink_path)
                if incorrect_target_base in target_path:
                    new_target_path = target_path.replace(incorrect_target_base, correct_target_base)
                    if os.path.exists(new_target_path):
                        logger.debug("Fixing Symlink", symlink={symlink_path}, target={new_target_path})
                        os.remove(symlink_path)
                        os.symlink(new_target_path, symlink_path)
                        fixed_count += 1
                    else:
                        missing_files.append(new_target_path)
        count += len(files)

    if fixed_count == 0:
        logger.info(f"Checked {count} total symlinks and found no symlinks to fix.")
    else:
        logger.info(f"Checked {count} total symlinks and fixed {fixed_count} symlinks.")

    if missing_files:
        for file in missing_files:
            logger.error("Missing", file=file)
        logger.error("Missing target files", missing_files=len(missing_files))

    logger.info("Finished fixing symlinks.")

def delete_dead_symlinks_and_targets(base_path):
    """
    Traverse through the directory, identify dead symlinks, and delete both the symlink and its target.

    :param base_path: Path where the symlinks are located (e.g., "/mnt/library/shows").
    """
    count = 0
    deleted_symlinks_count = 0
    deleted_files_count = 0
    logger.info("Starting to delete dead symlinks and their targets", base_path=base_path)

    for root, dirs, files in os.walk(base_path):
        for name in files + dirs:
            path = os.path.join(root, name)
            if os.path.islink(path):
                target_path = os.readlink(path)
                full_target_path = os.path.join(os.path.dirname(path), target_path)
                if not os.path.exists(full_target_path):
                    logger.warning("Dead symlink found, deleting symlink and target", symlink=path, target=full_target_path)
                    # Delete the target file if it exists (in case of broken paths or other issues)
                    if os.path.exists(full_target_path):
                        try:
                            os.remove(full_target_path)
                            deleted_files_count += 1
                            logger.info("Deleted target file", file=full_target_path)
                        except Exception as e:
                            logger.error("Failed to delete target file", file=full_target_path, error=str(e))
                    # Delete the symlink
                    try:
                        os.remove(path)
                        deleted_symlinks_count += 1
                        logger.info("Deleted symlink", symlink=path)
                    except Exception as e:
                        logger.error("Failed to delete symlink", symlink=path, error=str(e))
                count += 1

    logger.info("Cleanup completed", total_checked=count, symlinks_deleted=deleted_symlinks_count, files_deleted=deleted_files_count)


def resolve_path(base_path, target):
    """ Resolve the absolute path of a symlink target. """
    if os.path.isabs(target):
        return target
    return os.path.normpath(os.path.join(os.path.dirname(base_path), target))

def validate_media_file(file_path):
    """ Validate the media file using ffprobe. """
    ffprobe_path = "/usr/bin/ffprobe"  # Ensure this path is correct for your environment
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],  # noqa: S603
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True, check=False
        )
        return (file_path, result.returncode == 0)
    except Exception as e:
        logger.error("Failed to validate file with ffprobe", error=str(e), file_path=file_path)
        return (file_path, False)

def extended_validate_media_file(tasks):
    """ Validate media files using concurrency. """
    for future in as_completed(tasks):
        file_path, is_valid = future.result()
        if not is_valid:
            logger.warning("File exists but failed ffprobe validation", file_path=file_path)

def check_symlinks(symlink_dir, extended=False):
    """ Check symlinks and validate if the target files exist and are valid using concurrency. """
    logger.info("Checking symlinks in the directory", symlink_dir=symlink_dir)

    tasks = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for root, _, files in os.walk(symlink_dir):
            for file in files:
                full_path = os.path.join(root, file)
                if os.path.islink(full_path):
                    target_path = resolve_path(full_path, os.readlink(full_path))
                    if os.path.exists(target_path):
                        tasks.append(executor.submit(validate_media_file, target_path))
                    else:
                        logger.warning("Symlink target does not exist", symlink=full_path, target=target_path)

        # Handling the results as they complete
        if len(tasks) == 0 and not extended:
            logger.info("No symlinks found in the directory")
            return
        
        if extended:
            logger.info("Checking symlinks and further validating target files")
            extended_validate_media_file(tasks)

        logger.info("Symlink check completed", total_checked=len(tasks))

def find_file_in_directory(filename, search_path):
    """ Search for a file in a given directory recursively. """
    for root, _, files in os.walk(search_path):
        if filename in files:
            return os.path.join(root, filename)
    return None

def fix_symlink(symlink_path, new_target, dry_run):
    """ Fix the broken symlink with a new target. """
    if dry_run:
        logger.info("Dry run: would fix symlink", symlink=symlink_path, new_target=new_target)
    else:
        try:
            os.remove(symlink_path)
            os.symlink(new_target, symlink_path)
            logger.info("Fixed symlink", symlink=symlink_path, new_target=new_target)
        except Exception as e:
            logger.error("Failed to fix symlink", symlink=symlink_path, error=str(e))

def repair_broken_symlinks(base_path, rclone_path, dry_run=False):
    """ Identify and repair broken symlinks by searching for the target in the rclone path. """
    logger.info("Starting to repair broken symlinks", base_path=base_path)
    broken_count = 0
    repairable_count = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for root, _, files in os.walk(base_path):
            for file in files:
                full_path = os.path.join(root, file)
                if os.path.islink(full_path):
                    target_path = os.readlink(full_path)
                    if not os.path.exists(os.path.join(root, target_path)):
                        filename = os.path.basename(target_path)
                        futures[executor.submit(find_file_in_directory, filename, rclone_path)] = (full_path, filename)

        # Handle found files and fix symlinks
        for future in futures.as_completed(futures):
            symlink_path, filename = futures[future]
            new_target = future.result()
            if new_target:
                logger.info("Found new target for broken symlink", old_target=os.readlink(symlink_path), new_target=new_target)
                fix_symlink(symlink_path, new_target, dry_run)
                repairable_count += 1
            else:
                logger.warning("No new target found for broken symlink", symlink=symlink_path, filename=filename)
            broken_count += 1

    logger.info("Finished repairing symlinks", repairable=repairable_count, dead_symlinks=broken_count)

class SymlinkEventHandler(FileSystemEventHandler):
    """ Handler for filesystem events that checks for symlink changes. """

    def __init__(self, base_path):
        self.base_path = base_path

    def on_created(self, event):
        """ This method is called when a new file or directory is created. """
        if not event.is_directory:  # noqa: SIM102
            if os.path.islink(event.src_path):
                target_path = os.readlink(event.src_path)
                if not os.path.exists(os.path.join(os.path.dirname(event.src_path), target_path)):
                    logger.warning("New dead symlink detected", symlink=event.src_path, target=target_path)

    def on_deleted(self, event):
        """ This method is called when a file or directory is deleted. """
        if not event.is_directory:  # noqa: SIM102
            if os.path.islink(event.src_path):
                logger.info("Symlink deleted", symlink=event.src_path)

    def on_modified(self, event):
        """ This method is called when a file or directory is modified. """
        if not event.is_directory:  # noqa: SIM102
            if os.path.islink(event.src_path):
                target_path = os.readlink(event.src_path)
                if not os.path.exists(os.path.join(os.path.dirname(event.src_path), target_path)):
                    logger.warning("Existing symlink now points to non-existent target", symlink=event.src_path, target=target_path)

def start_monitoring(base_path):
    """ Start monitoring the directory for changes to symlinks. """
    event_handler = SymlinkEventHandler(base_path=base_path)
    observer = Observer()
    observer.schedule(event_handler, path=base_path, recursive=True)
    observer.start()
    logger.info("Started monitoring symlinks in directory", directory=base_path)
    try:
        while True:
            pass  # Keep the script running
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    rclone_dir = "/mnt/zurg"
    symlink_dir = "/mnt/library"           # Path where the symlinks are located (recursive)
    incorrect_target_base = "/mnt/zurg"  # Incorrect part of the target path
    correct_target_base = "/mnt/zurg"    # Correct part of the target path
    # delete_dead_symlinks_and_targets(symlink_dir) # Do not enable! This will delete files!

    # fix_symlinks(symlink_dir, incorrect_target_base, correct_target_base)
    # check_symlinks(symlink_dir)
    # repair_broken_symlinks(symlink_dir, rclone_dir, dry_run=True)

    check_dead_symlinks(symlink_dir)
    start_monitoring(symlink_dir)
    sys.exit(0)
