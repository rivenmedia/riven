import time
from datetime import datetime

from rich.live import Live
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from program.db.db import db
from program.media.item import MediaItem, Movie, Show
from program.service_manager import service_manager
from program.services.indexers.composite import CompositeIndexer
from program.services.libraries.symlink import SymlinkLibrary
from program.settings.manager import settings_manager
from program.utils.logging import create_progress_bar, logger

from . import db_functions


def _enhance_item(item: MediaItem) -> MediaItem | None:
    try:
        return next(service_manager.services[CompositeIndexer].run(item, log_msg=False))
    except StopIteration:
        return None

def _should_skip_item(item, added_items, session):
    """Check if item should be skipped due to duplicates."""
    if not item or item.log_string in added_items:
        return True, f"Duplicate symlink directory found for {item.log_string if item else 'Unknown'}"
    
    if db_functions.get_item_by_id(item.id, session=session):
        return True, f"Duplicate item found in database for id: {item.id}"
    
    return False, ""

def _enhance_item_with_retry(item):
    """Enhance item with Trakt data, handling rate limits."""
    try:
        enhanced_item = _enhance_item(item)
        if not enhanced_item:
            return None, f"Failed to enhance {item.log_string} with Trakt Indexer"
        return enhanced_item, ""
    except Exception as e:
        if "rate limit" in str(e).lower() or "429" in str(e):
            logger.warning(f"Rate limit hit for {item.log_string}, waiting 10 seconds...")
            time.sleep(10)
            try:
                enhanced_item = _enhance_item(item)
                if not enhanced_item:
                    return None, f"Failed to enhance {item.log_string} after retry"
                return enhanced_item, ""
            except Exception as retry_e:
                return None, f"Rate limit retry failed for {item.log_string}: {str(retry_e)}"
        else:
            return None, f"Error enhancing {item.log_string}: {str(e)}"

def _safe_commit(session, item_id=None):
    """Safely commit session with duplicate key handling."""
    try:
        session.commit()
    except IntegrityError as e:
        if "duplicate key value violates unique constraint" in str(e):
            if item_id:
                logger.debug(f"Item with ID {item_id} was added by another process during symlink initialization")
            else:
                logger.debug("Some items were added by another process during symlink initialization")
            session.rollback()
        else:
            raise

def _process_symlink_item(item, session, added_items, progress, task, processed_count):
    """Process a single symlink item."""
    # Check for duplicates
    should_skip, skip_reason = _should_skip_item(item, added_items, session)
    if should_skip:
        return skip_reason, f"Skipped duplicate: {item.log_string if item else 'Unknown'}"

    # Enhance item
    enhanced_item, error = _enhance_item_with_retry(item)
    if not enhanced_item:
        return error, f"Failed to enhance: {item.log_string}"

    # Save to database
    enhanced_item.store_state()
    session.add(enhanced_item)
    added_items.add(item.log_string)

    # Periodic commit
    if processed_count % 25 == 0:
        _safe_commit(session, enhanced_item.id)

    return "", f"Successfully Indexed {enhanced_item.log_string}"

def _init_db_from_symlinks():
    """Initialize the database from symlinks."""
    with db.Session() as session:
        # Check if database is empty
        if not session.execute(select(func.count(MediaItem.id))).scalar_one():
            if not settings_manager.settings.map_metadata:
                return

            logger.log("PROGRAM", "Collecting items from symlinks, this may take a while depending on library size")
            start_time = datetime.now()

            try:
                symlink_service = service_manager.get_service(SymlinkLibrary)
                if not symlink_service or not getattr(symlink_service, "initialized", False):
                    logger.error("SymlinkLibrary service is not available or failed validation; skipping symlink initialization")
                    return
                items = symlink_service.run()
                errors = []
                added_items = set()

                # Convert items to list and get total count
                items_list = [item for item in items if isinstance(item, (Movie, Show))]
                total_items = len(items_list)
                progress, console = create_progress_bar(total_items)
                task = progress.add_task("Enriching items with metadata", total=total_items, log="")
                processed_count = 0

                with Live(progress, console=console, refresh_per_second=10):
                    for item in items_list:
                        processed_count += 1
                        try:
                            error, log_message = _process_symlink_item(
                                item, session, added_items, progress, task, processed_count
                            )
                            if error:
                                errors.append(error)
                            progress.update(task, advance=1, log=log_message)
                        except Exception as e:
                            errors.append(f"Unexpected error for {item.log_string}: {str(e)}")
                            progress.update(task, advance=1, log=f"Error: {item.log_string}")
                            continue

                    # Final commit for any remaining items
                    _safe_commit(session)
                    progress.update(task, log="Finished Indexing Symlinks!")
                    elapsed_time = datetime.now() - start_time

                if errors:
                    logger.error("Errors encountered during initialization")
                    for error in errors:
                        logger.error(error)

            except Exception as e:
                session.rollback()
                logger.error(f"Failed to initialize database from symlinks: {type(e).__name__}: {e}")
                return

            total_seconds = elapsed_time.total_seconds()
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            logger.success(f"Database initialized, time taken: h{int(hours):02d}:m{int(minutes):02d}:s{int(seconds):02d}")