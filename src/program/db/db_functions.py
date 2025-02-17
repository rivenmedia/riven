from dataclasses import dataclass
from datetime import datetime
import os
import shutil
from threading import Event
from typing import TYPE_CHECKING, List, Optional, Union

from loguru import logger
from sqlalchemy import delete, insert, inspect, or_, select, text
from sqlalchemy.orm import Session, selectinload, aliased

import alembic

from program.media.stream import Stream, StreamBlacklistRelation, StreamRelation
from program.services.libraries.symlink import fix_broken_symlinks
from program.settings.manager import settings_manager
from program.utils import root_dir
from program.media.state import States

from .db import db

if TYPE_CHECKING:
    from program.media.item import MediaItem


@dataclass
class ItemFilter:
    """Filter configuration for MediaItem queries in the database."""
    id: Optional[Union[str, List[str]]] = None
    type: Optional[Union[str, List[str]]] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    title: Optional[str] = None

    states: Optional[List[States]] = None
    is_released: Optional[bool] = None
    is_anime: Optional[bool] = None
    is_symlinked: Optional[bool] = None
    is_scraped: Optional[bool] = None

    requested_after: Optional[datetime] = None
    requested_before: Optional[datetime] = None
    aired_after: Optional[datetime] = None
    aired_before: Optional[datetime] = None
    scraped_after: Optional[datetime] = None
    scraped_before: Optional[datetime] = None

    year: Optional[Union[int, List[int]]] = None
    country: Optional[str] = None
    language: Optional[str] = None
    requested_by: Optional[str] = None

    has_file: Optional[bool] = None
    has_folder: Optional[bool] = None
    has_symlink: Optional[bool] = None
    filepath: Optional[str] = None
    folder: Optional[str] = None
    symlink_path: Optional[str] = None

    season_number: Optional[int] = None
    episode_number: Optional[int] = None

    failed_attempts: Optional[int] = None
    scraped_times: Optional[int] = None
    symlinked_times: Optional[int] = None

    load_streams: bool = False
    load_blacklisted_streams: bool = False
    load_subtitles: bool = False
    load_children: bool = True
    
    def __post_init__(self):
        # Convert single values to lists where appropriate
        """
        Post-initialization processing for normalizing filter attributes.
        
        This method is automatically called after an ItemFilter instance is initialized. It ensures that
        attributes expected to be lists are properly formatted. Specifically:
        - If 'type' is None, it is set to ["movie", "show"] by default.
        - If 'type' is provided as a single string, it is converted into a list containing that string.
        - If 'id' is provided as a single string, it is converted into a list containing that value.
        - If 'year' is provided as a single integer, it is converted into a list containing that integer.
        """
        if self.type is None:
            self.type = ["movie", "show"]
        if isinstance(self.type, str):
            self.type = [self.type]
        if isinstance(self.id, str):
            self.id = [self.id]
        if isinstance(self.year, int):
            self.year = [self.year]

def get_items_from_filter(
    session: Session = None,
    filter: ItemFilter = None,
    limit: int = None,
) -> List["MediaItem"]:
    """
    Retrieve a list of MediaItem objects from the database that match the specified filter criteria.
    
    This function constructs an SQLAlchemy query using an ItemFilter instance to apply a variety of filtering
    conditions on MediaItem records. It supports filtering by unique identifiers, media type, external IDs,
    title (with case-insensitive search), state, date ranges (for request, air, and scrape timestamps), and other
    metadata such as language, country, file or folder presence, and more. Additional filtering for seasons and
    episodes is implemented via join operations when season and episode numbers are provided. The function also
    supports eager loading of related entities (streams, blacklisted streams, subtitles, and child items) based on
    flags in the filter.
    
    Parameters:
        session (Session, optional): An existing SQLAlchemy session to use for the query. If not provided, a new session
            will be created.
        filter (ItemFilter, optional): An instance of ItemFilter containing filtering criteria. Attributes of the
            filter determine which conditions will be applied to the query.
        limit (int, optional): The maximum number of MediaItem objects to return. If None, all matching items are retrieved.
    
    Returns:
        List[MediaItem]: A list of MediaItem objects that meet the provided filter criteria.
    
    Example:
        filter_criteria = ItemFilter(title="Example", is_anime=True, load_streams=True)
        media_items = get_items_from_filter(session=my_session, filter=filter_criteria, limit=10)
        for item in media_items:
            print(item.title)
    """
    from program.media.item import Episode, MediaItem, Season, Show
    
    _session = session if session else db.Session()
    stmt = _session.query(MediaItem)

    if filter.id:
        stmt = stmt.where(MediaItem.id.in_(filter.id))
    else:
        if filter.season_number and not filter.episode_number:
            stmt = stmt.where(MediaItem.type == "season")
        elif filter.season_number and filter.episode_number:
            stmt = stmt.where(MediaItem.type == "episode")
        else:
            stmt = stmt.where(MediaItem.type.in_(filter.type))
    if filter.tvdb_id:
        stmt = stmt.where(MediaItem.tvdb_id == filter.tvdb_id)
    if filter.tmdb_id:
        stmt = stmt.where(MediaItem.tmdb_id == filter.tmdb_id)
    if filter.title:
        stmt = stmt.where(MediaItem.title.ilike(f"%{filter.title}%"))

    if filter.states:
        stmt = stmt.where(MediaItem.last_state.in_(filter.states))
    if filter.is_anime is not None:
        stmt = stmt.where(MediaItem.is_anime == filter.is_anime)
    if filter.is_symlinked is not None:
        stmt = stmt.where(MediaItem.symlinked == filter.is_symlinked)

    if filter.requested_after:
        stmt = stmt.where(MediaItem.requested_at >= filter.requested_after)
    if filter.requested_before:
        stmt = stmt.where(MediaItem.requested_at <= filter.requested_before)
    if filter.aired_after:
        stmt = stmt.where(MediaItem.aired_at >= filter.aired_after)
    if filter.aired_before:
        stmt = stmt.where(MediaItem.aired_at <= filter.aired_before)
    if filter.scraped_after:
        stmt = stmt.where(MediaItem.scraped_at >= filter.scraped_after)
    if filter.scraped_before:
        stmt = stmt.where(MediaItem.scraped_at <= filter.scraped_before)

    if filter.year:
        stmt = stmt.where(MediaItem.year.in_(filter.year))
    if filter.country:
        stmt = stmt.where(MediaItem.country == filter.country)
    if filter.language:
        stmt = stmt.where(MediaItem.language == filter.language)
    if filter.requested_by:
        stmt = stmt.where(MediaItem.requested_by == filter.requested_by)

    if filter.has_file is not None:
        if filter.has_file:
            stmt = stmt.where(MediaItem.file is None)
        else:
            stmt = stmt.where(MediaItem.file is not None)
    if filter.has_folder is not None:
        if filter.has_folder:
            stmt = stmt.where(MediaItem.folder is not None)
        else:
            stmt = stmt.where(MediaItem.folder is None)
    if filter.filepath:
        stmt = stmt.where(MediaItem.file == filter.filepath)
    if filter.folder:
        stmt = stmt.where(MediaItem.folder == filter.folder)
    if filter.symlink_path:
        stmt = stmt.where(MediaItem.symlink_path == filter.symlink_path)

    if filter.failed_attempts is not None:
        stmt = stmt.where(MediaItem.failed_attempts == filter.failed_attempts)
    if filter.scraped_times is not None:
        stmt = stmt.where(MediaItem.scraped_times == filter.scraped_times)
    if filter.symlinked_times is not None:
        stmt = stmt.where(MediaItem.symlinked_times == filter.symlinked_times)

    if filter.season_number is not None:
        season_alias = aliased(Season)
        stmt = (
            stmt.join(season_alias, Season.id == Episode.parent_id)
            .where(season_alias.number == filter.season_number)
        )
    
    if filter.episode_number is not None:
        stmt = stmt.where(Episode.number == filter.episode_number)

    options = []
    if filter.load_streams:
        options.extend([
            selectinload(MediaItem.streams),
        ])
    if filter.load_blacklisted_streams:
        options.extend([
            selectinload(MediaItem.blacklisted_streams),
        ])
    if filter.load_subtitles:
        options.extend([
            selectinload(MediaItem.subtitles),
        ])
    if filter.load_children:
        options.extend([
            selectinload(Show.seasons)
            .selectinload(Season.episodes)
        ])
    
    if options:
        stmt = stmt.options(*options)
    
    with _session:
        if limit:
            stmt = stmt.limit(limit)
        return _session.execute(stmt).unique().scalars().all()

def get_item_by_id(item_id: str, item_types: list[str] = None, session: Session = None) -> "MediaItem":
    """
    Retrieve a MediaItem from the database using its unique identifier.
    
    This function constructs a SQLAlchemy query to fetch a MediaItem that matches the provided
    item_id. It optionally restricts the search to include only media items of specified types.
    Related entities such as seasons and episodes are eagerly loaded using selectinload to
    optimize performance. If a session is provided, it is used; otherwise, a new session is created.
    
    Parameters:
        item_id (str): The unique identifier of the media item. If falsy, the function returns None.
        item_types (list[str], optional): A list of media item types (e.g., "movie", "show") to narrow
            the query. Defaults to None.
        session (Session, optional): An existing SQLAlchemy session for executing the query. If None,
            a new session is obtained automatically.
    
    Returns:
        MediaItem or None: The MediaItem matching the item_id if found; otherwise, None.
    
    Example:
        >>> item = get_item_by_id("abc123", item_types=["movie"])
        >>> if item:
        ...     print("Media item found:", item.title)
        ... else:
        ...     print("Media item not found.")
    """
    if not item_id:
        return None

    from program.media.item import MediaItem, Season, Show
    _session = session if session else db.Session()

    with _session:
        query = (select(MediaItem)
            .where(MediaItem.id == item_id)
            .options(
                selectinload(Show.seasons)
                .selectinload(Season.episodes)
            ))
        if item_types:
            query = query.where(MediaItem.type.in_(item_types))

        item = _session.execute(query).unique().scalar_one_or_none()
        if item:
            _session.expunge(item)
        return item

def get_items_by_ids(ids: list, item_types: list[str] = None, session: Session = None) -> list["MediaItem"]:
    """
    Retrieve multiple MediaItem objects corresponding to the provided list of IDs.
    
    This function iterates over the given list of IDs and retrieves each MediaItem by invoking
    the get_item_by_id function. Optionally, the lookup can be filtered by a list of item types
    and executed within a provided SQLAlchemy session.
    
    Parameters:
        ids (list): A list of unique identifiers for the MediaItem objects.
        item_types (list[str], optional): A list of item type strings to filter the lookup.
            If specified, only MediaItems matching these types will be retrieved. Defaults to None.
        session (Session, optional): An optional SQLAlchemy session to use for database queries.
            Defaults to None.
    
    Returns:
        list[MediaItem]: A list of MediaItem objects corresponding to the provided IDs.
            If a MediaItem is not found for a given ID, None will be included in its place.
    
    Example:
        >>> items = get_items_by_ids(["1", "2", "3"], item_types=["movie"], session=db_session)
        >>> for item in items:
        ...     if item is not None:
        ...         print(item.title)
    """
    items = []
    for id in ids:
        items.append(get_item_by_id(id, item_types,  session))
    return items

def get_item_by_external_id(imdb_id: str = None, tvdb_id: int = None, tmdb_id: int = None, session: Session = None) -> "MediaItem":
    """
    Retrieve a MediaItem using one of its external identifiers (IMDb, TVDB, or TMDB).
    
    This function builds a SQLAlchemy query to fetch a MediaItem from the database, limiting the search to items of type "movie" or "show". For shows, related seasons and their episodes are eagerly loaded using the selectin loading strategy. A session is used to execute the query, and if a matching item is found, it is detached from the session before being returned.
    
    Parameters:
        imdb_id (str, optional): The IMDb identifier of the media item.
        tvdb_id (int, optional): The TVDB identifier of the media item.
        tmdb_id (int, optional): The TMDB identifier of the media item.
        session (Session, optional): An existing SQLAlchemy session to be used for the query. If not provided, a new session is created.
    
    Returns:
        MediaItem or None: The MediaItem matching the provided external identifier, or None if no item is found.
    
    Raises:
        ValueError: If none of the external identifiers (IMDb, TVDB, or TMDB) is provided.
    """
    from program.media.item import MediaItem, Season, Show

    _session = session if session else db.Session()
    query = (
        select(MediaItem)
        .options(
            selectinload(Show.seasons)
            .selectinload(Season.episodes)
        )
        .where(or_(MediaItem.type == "movie", MediaItem.type == "show"))
    )

    if imdb_id:
        query = query.where(MediaItem.imdb_id == imdb_id)
    elif tvdb_id:
        query = query.where(MediaItem.tvdb_id == tvdb_id)
    elif tmdb_id:
        query = query.where(MediaItem.tmdb_id == tmdb_id)
    else:
        raise ValueError("One of the external ids must be given")

    with _session:
        item = _session.execute(query).unique().scalar_one_or_none()
        if item:
            _session.expunge(item)
        return item

def delete_media_item(item: "MediaItem"):
    """
    Delete a MediaItem and its associated relationships from the database.
    
    This function creates a new database session, merges the provided MediaItem instance to
    attach it to the session, and then deletes it. All related entities configured with cascading
    delete options will also be removed. The transaction is committed immediately to persist the change.
    
    Parameters:
        item (MediaItem): The media item instance to be deleted. It should represent an existing record in the database.
    
    Returns:
        bool: True if the deletion was successfully committed.
    
    Raises:
        sqlalchemy.exc.SQLAlchemyError: If an error occurs during the deletion process.
    """
    with db.Session() as session:
        item = session.merge(item)
        session.delete(item)
        session.commit()

def delete_media_item_by_id(media_item_id: str, batch_size: int = 30) -> bool:
    """
    Delete a media item and its associated records by ID.
    
    Depending on the media item's type, this function performs the following:
        - For a show, it batch deletes the associated seasons and episodes, then deletes the show record.
        - For a movie, it deletes the movie record.
        - For a season, it batch deletes the associated episodes and then deletes the season record.
        - For an episode, it directly deletes the episode record.
    After handling type-specific deletions, the primary MediaItem record is deleted.
    
    Parameters:
        media_item_id (str): The unique identifier of the media item to delete. Must not be empty.
        batch_size (int, optional): The number of records to process per batch when deleting seasons and episodes. Defaults to 30.
    
    Returns:
        bool: True if the deletion process completes successfully; False otherwise.
    
    Raises:
        IntegrityError: Captured and logged if a database integrity error occurs during deletion.
        Exception: Captured and logged if any unexpected error occurs during the deletion process.
    
    Example:
        result = delete_media_item_by_id("12345")
        if result:
            print("Media item and its related records were successfully deleted.")
        else:
            print("Failed to delete the media item.")
    """
    from sqlalchemy.exc import IntegrityError
    from program.media.item import Episode, MediaItem, Movie, Season, Show

    if not media_item_id:
        logger.error("Item ID can not be empty")
        return False

    with db.Session() as session:
        try:
            # First, retrieve the media item's type
            media_item_type = session.execute(
                select(MediaItem.type)
                .where(MediaItem.id == media_item_id)
            ).scalar_one_or_none()

            if not media_item_type:
                logger.error(f"No item found with ID {media_item_id}")
                return False

            if media_item_type == "show":
                season_ids = session.execute(
                    select(Season.id).where(Season.parent_id == media_item_id)
                ).scalars().all()

                delete_seasons_and_episodes(session, season_ids, batch_size)
                session.execute(delete(Show).where(Show.id == media_item_id))

            if media_item_type == "movie":
                session.execute(delete(Movie).where(Movie.id == media_item_id))

            if media_item_type == "season":
                delete_seasons_and_episodes(session, [media_item_id], batch_size)
                session.execute(delete(Season).where(Season.id == media_item_id))

            if media_item_type == "episode":
                session.execute(delete(Episode).where(Episode.id == media_item_id))

            session.execute(delete(MediaItem).where(MediaItem.id == media_item_id))
            session.commit()
            return True

        except IntegrityError as e:
            logger.error(f"Integrity error while deleting media item with ID {media_item_id}: {e}")
            session.rollback()
            return False
        except Exception as e:
            logger.error(f"Unexpected error while deleting media item with ID {media_item_id}: {e}")
            session.rollback()
            return False

def delete_seasons_and_episodes(session: Session, season_ids: list[str], batch_size: int = 30):
    """
    Delete seasons and their related episodes from the database in batch operations.
    
    This function processes each season ID in the provided list by:
        1. Retrieving the season record.
        2. Deleting associated entries for stream relations, stream blacklist relations, and subtitles,
           and committing these deletions.
        3. Deleting episodes linked to the season in batches determined by `batch_size`. Each batch of episode
           deletions is committed before proceeding to the next.
        4. Finally, deleting the season record itself and committing the final deletion.
    
    Parameters:
        session (Session): The active SQLAlchemy session for executing database operations.
        season_ids (list[str]): List of season identifiers to delete.
        batch_size (int, optional): Maximum number of episodes to delete per batch. Defaults to 30.
    
    Raises:
        SQLAlchemyError: Propagates any database errors encountered during the deletion process.
    
    Returns:
        None
    """
    from program.media.item import Episode, Season
    from program.media.stream import StreamBlacklistRelation, StreamRelation
    from program.media.subtitle import Subtitle

    for season_id in season_ids:
        season = session.query(Season).get(season_id)
        session.execute(delete(StreamRelation).where(StreamRelation.parent_id == season_id))
        session.execute(delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == season_id))
        session.execute(delete(Subtitle).where(Subtitle.parent_id == season_id))
        session.commit()

        while True:
            episode_ids = session.execute(
                select(Episode.id).where(Episode.parent_id == season_id).limit(batch_size)
            ).scalars().all()

            if not episode_ids:
                break

            session.execute(delete(Episode).where(Episode.id.in_(episode_ids)))
            session.commit()

        session.delete(season)
        session.commit()

def reset_media_item(item: "MediaItem"):
    """
    Reset the state of the given MediaItem instance.
    
    This function attaches the provided MediaItem to an active database session by merging it,
    calls its `reset` method to perform any state reinitialization, and commits the changes to persist
    the update in the database. Use this function to ensure that the MediaItem's in-memory state is
    synchronized with the database record.
    
    Parameters:
        item (MediaItem): The media item instance to reset. This may be a detached instance.
    
    Returns:
        None
    
    Raises:
        Exception: Propagates any exception raised during the commit operation.
    """
    with db.Session() as session:
        item = session.merge(item)
        item.reset()
        session.commit()

def reset_streams(item: "MediaItem"):
    """
    Reset all stream associations for a MediaItem.
    
    This function removes all stream-related entries associated with the given MediaItem by deleting records
    from the StreamRelation table (using the MediaItem's id as the parent_id) and from the StreamBlacklistRelation
    table (using the MediaItem's id as the media_item_id). The deletions are executed within a new database session 
    and committed to ensure that the changes are persisted.
    
    Parameters:
        item (MediaItem): The media item for which stream and blacklist associations will be cleared.
    
    Returns:
        bool: True if the stream associations were successfully reset and the transaction committed.
    
    Raises:
        SQLAlchemyError: If an error occurs during the deletion operations or commit.
    """
    with db.Session() as session:
        session.execute(delete(StreamRelation).where(StreamRelation.parent_id == item.id))
        session.execute(delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == item.id))
        session.commit()

def clear_streams(item: "MediaItem"):
    """
    Clears all stream associations for the specified media item by delegating to the reset_streams function.
    
    This wrapper function removes all stream relationships for the provided media item. It relies on the underlying reset_streams implementation to perform the actual operation.
    
    Parameters:
        item (MediaItem): The media item whose stream relationships are to be cleared.
    
    Returns:
        bool: True if the streams were successfully cleared, False otherwise.
    """
    reset_streams(item)

def clear_streams_by_id(media_item_id: str):
    """Clear all streams for a media item by the MediaItem id."""
    with db.Session() as session:
        session.execute(
            delete(StreamRelation).where(StreamRelation.parent_id == media_item_id)
        )
        session.execute(
            delete(StreamBlacklistRelation).where(StreamBlacklistRelation.media_item_id == media_item_id)
        )
        session.commit()

def blacklist_stream(item: "MediaItem", stream: Stream, session: Session = None) -> bool:
    """Blacklist a stream for a media item."""
    close_session = False
    if session is None:
        session = db.Session()
        item = session.execute(select(type(item)).where(type(item).id == item.id)).unique().scalar_one()
        close_session = True

    try:
        item = session.merge(item)
        association_exists = session.query(
            session.query(StreamRelation)
            .filter(StreamRelation.parent_id == item.id)
            .filter(StreamRelation.child_id == stream.id)
            .exists()
        ).scalar()

        if association_exists:
            session.execute(
                delete(StreamRelation)
                .where(StreamRelation.parent_id == item.id)
                .where(StreamRelation.child_id == stream.id)
            )
            session.execute(
                insert(StreamBlacklistRelation)
                .values(media_item_id=item.id, stream_id=stream.id)
            )
            item.store_state()
            session.commit()
            return True
        return False
    finally:
        if close_session:
            session.close()

def unblacklist_stream(item: "MediaItem", stream: Stream, session: Session = None) -> bool:
    """
    Remove a stream from the blacklist for a media item.
    
    This function checks if the given stream is currently blacklisted for the specified media item.
    If a blacklist association exists, it removes the entry from the StreamBlacklistRelation table and inserts
    a corresponding record into the StreamRelation table, effectively unblacklisting the stream.
    The media item's state is updated using its `store_state()` method, and all changes are committed.
    If no blacklist association is found, the function returns False.
    
    Parameters:
        item (MediaItem): The media item for which the stream should be unblacklisted.
        stream (Stream): The stream to remove from the blacklist.
        session (Session, optional): An active SQLAlchemy session. If not provided, a new session is created
                                     and closed after the operation.
    
    Returns:
        bool: True if the stream was successfully unblacklisted, False otherwise.
    """
    close_session = False
    if session is None:
        session = db.Session()
        item = session.execute(select(type(item)).where(type(item).id == item.id)).unique().scalar_one()
        close_session = True

    try:
        item = session.merge(item)
        association_exists = session.query(
            session.query(StreamBlacklistRelation)
            .filter(StreamBlacklistRelation.media_item_id == item.id)
            .filter(StreamBlacklistRelation.stream_id == stream.id)
            .exists()
        ).scalar()

        if association_exists:
            session.execute(
                delete(StreamBlacklistRelation)
                .where(StreamBlacklistRelation.media_item_id == item.id)
                .where(StreamBlacklistRelation.stream_id == stream.id)
            )
            session.execute(
                insert(StreamRelation)
                .values(parent_id=item.id, child_id=stream.id)
            )
            item.store_state()
            session.commit()
            return True
        return False
    finally:
        if close_session:
            session.close()

def get_item_ids(session: Session, item_id: str) -> tuple[str, list[str]]:
    """
    Retrieve the primary media item ID along with its related child item IDs.
    
    This function determines the type of a media item by querying the database using the provided item_id. Based on the item's type:
    - If the item is of type "show", the function retrieves all season IDs linked to the show and, for each season, gathers the associated episode IDs.
    - If the item is of type "season", the function retrieves all episode IDs associated with that season.
    - For other item types, no related IDs are collected.
    
    Parameters:
        session (Session): An active SQLAlchemy session used for executing database queries.
        item_id (str): The unique identifier of the MediaItem.
    
    Returns:
        tuple[str, list[str]]: A tuple where the first element is the original item_id and the second element is a list of related item IDs (which may include season and episode IDs).
    """
    from program.media.item import Episode, MediaItem, Season

    item_type = session.query(MediaItem.type).filter(MediaItem.id == item_id).scalar()
    related_ids = []

    if item_type == "show":
        season_ids = session.execute(
            select(Season.id).where(Season.parent_id == item_id)
        ).scalars().all()

        for season_id in season_ids:
            episode_ids = session.execute(
                select(Episode.id).where(Episode.parent_id == season_id)
            ).scalars().all()
            related_ids.extend(episode_ids)
        related_ids.extend(season_ids)

    elif item_type == "season":
        episode_ids = session.execute(
            select(Episode.id).where(Episode.parent_id == item_id)
        ).scalars().all()
        related_ids.extend(episode_ids)

    return item_id, related_ids

def run_thread_with_db_item(fn, service, program, event: Event, cancellation_event: Event) -> Optional[str]:
    """
    Executes a threaded operation on a MediaItem based on an event and manages corresponding database state updates.
    
    This function retrieves a MediaItem from the database using the details provided in the event object. If the event
    contains an 'item_id', it fetches and merges that item, then passes it to the generator function 'fn'. The function
    expects 'fn' to yield a result that can be either a MediaItem instance or a tuple of (MediaItem, run_at). Depending
    on the yielded result and its type, the function returns either the MediaItem's id or a tuple containing the id and
    the run_at timestamp. If the event contains a 'content_item' instead, it processes that item similarly and returns its id.
    In the absence of an event (i.e. for content services that do not pass events), the function iterates over items yielded
    by 'fn' and adds any MediaItem instances to the program’s entity manager queue using the provided service.
    
    Parameters:
        fn (Callable[[MediaItem], Iterator]): A generator or callable that takes a MediaItem and yields processing results.
            The yielded result may be a MediaItem or a tuple in the form (MediaItem, run_at).
        service (Any): A service object or function (expected to have a __name__ attribute) used for logging and queue management.
        program (Any): The program context containing the entity manager (em) for handling MediaItems.
        event (Event): An event object that may include an 'item_id' or 'content_item' attribute to specify the target MediaItem.
        cancellation_event (Event): An event used to signal cancellation of the operation. If set, database commits are skipped.
    
    Returns:
        Optional[Union[str, Tuple[str, Any]]]: The identifier (id) of the processed MediaItem, or a tuple (id, run_at) if the result
            yielded by 'fn' includes a scheduled run time. Returns None if processing does not yield a result, fails, or is cancelled.
    
    Side Effects:
        - Retrieves, merges, and updates MediaItem(s) in the database.
        - Commits state changes for the MediaItem or its parent objects based on its type ('episode', 'season', etc.).
        - Logs debug or warning messages if unexpected results are encountered.
        - Modifies the program’s entity manager queue by adding or removing items based on processing outcomes.
    """
    from program.media.item import MediaItem
    if event:
        with db.Session() as session:
            if event.item_id:
                input_item = get_item_by_id(event.item_id, session=session)
                if input_item:
                    input_item = session.merge(input_item)
                    res = next(fn(input_item), None)
                    if res:
                        if isinstance(res, tuple):
                            item, run_at = res
                            res = item.id, run_at
                        else:
                            item = res
                            res = item.id
                        if not isinstance(item, MediaItem):
                            logger.log("PROGRAM", f"Service {service.__name__} emitted {item} from input item {input_item} of type {type(item).__name__}, backing off.")
                            program.em.remove_id_from_queues(input_item.id)

                        if not cancellation_event.is_set():
                            # Update parent item
                            if input_item.type == "episode":
                                input_item.parent.parent.store_state()
                            elif input_item.type == "season":
                                input_item.parent.store_state()
                            else:
                                input_item.store_state()
                            session.commit()
                        return res
            # This is in bad need of indexing...
            if event.content_item:
                indexed_item = next(fn(event.content_item), None)
                if indexed_item is None:
                    logger.debug(f"Unable to index {event.content_item.log_string}")
                    return None
                indexed_item.store_state()
                session.add(indexed_item)
                item_id = indexed_item.id
                if not cancellation_event.is_set():
                    session.commit()
                return item_id
    # Content services dont pass events, get ready for a ride!
    else:
        for i in fn():
            if isinstance(i, MediaItem):
                i = [i]
            if isinstance(i, list):
                for item in i:
                    if isinstance(item, MediaItem):
                        program.em.add_item(item, service)
    return None

def hard_reset_database() -> None:
    """
    Perform a hard reset of the database while preserving migration capability.
    
    This function resets the entire database to a fresh state. It first attempts to store the current Alembic
    migration version, then performs the following operations based on the database type:
      - PostgreSQL: Terminates existing connections, drops the "public" schema (with cascade), recreates it,
        and resets schema privileges.
      - SQLite: Disables foreign key constraints, drops all tables, and re-enables foreign key constraints.
    
    After clearing the schema, all tables are recreated from the ORM metadata. If a previous Alembic version was
    found, it is restored; otherwise, the database is stamped with the "head" revision via Alembic.
    
    Finally, the function verifies the database state by checking that all tables exist and that the Alembic
    version is correctly set.
    
    Returns:
        None
    
    Raises:
        Exception: Propagates any exception encountered during the reset or verification operations.
    """
    logger.log("DATABASE", "Starting Hard Reset of Database")

    # Store current alembic version before reset
    current_version = None
    try:
        with db.engine.connect() as connection:
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            current_version = result.scalar()
    except Exception:
        pass

    with db.engine.connect() as connection:
        # Ensure we're in AUTOCOMMIT mode for PostgreSQL schema operations
        connection = connection.execution_options(isolation_level="AUTOCOMMIT")

        try:
            # Terminate existing connections for PostgreSQL
            if db.engine.name == "postgresql":
                connection.execute(text("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    AND pid <> pg_backend_pid()
                """))

                # Drop and recreate schema
                connection.execute(text("DROP SCHEMA public CASCADE"))
                connection.execute(text("CREATE SCHEMA public"))
                connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
                logger.log("DATABASE", "Schema reset complete")

            # For SQLite, drop all tables
            elif db.engine.name == "sqlite":
                connection.execute(text("PRAGMA foreign_keys = OFF"))

                # Get all tables
                tables = connection.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )).scalars().all()

                # Drop each table
                for table in tables:
                    connection.execute(text(f"DROP TABLE IF EXISTS {table}"))

                connection.execute(text("PRAGMA foreign_keys = ON"))
                logger.log("DATABASE", "All tables dropped")

            # Recreate all tables
            db.Model.metadata.create_all(connection)
            logger.log("DATABASE", "All tables recreated")

            # If we had a previous version, restore it
            if current_version:
                connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
                connection.execute(text("INSERT INTO alembic_version (version_num) VALUES (:version)"), 
                                {"version": current_version})
                logger.log("DATABASE", f"Restored alembic version to: {current_version}")
            else:
                # Stamp with head version if no previous version
                alembic.stamp("head")
                logger.log("DATABASE", "Database stamped with head revision")

        except Exception as e:
            logger.error(f"Error during database reset: {str(e)}")
            raise

    logger.log("DATABASE", "Hard Reset Complete")

    # Verify database state
    try:
        with db.engine.connect() as connection:
            # Check if all tables exist
            inspector = inspect(db.engine)
            all_tables = inspector.get_table_names()
            logger.log("DATABASE", f"Verified tables: {', '.join(all_tables)}")

            # Verify alembic version
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            version = result.scalar()
            logger.log("DATABASE", f"Verified alembic version: {version}")

    except Exception as e:
        logger.error(f"Error verifying database state: {str(e)}")
        raise

def hard_reset_database_pre_migration() -> None:
    """
    Performs a hard reset of the database prior to running migrations.
    
    This function drops all existing tables defined in the SQLAlchemy metadata, including the Alembic version table if present, and then recreates the tables using the current model definitions. During this process, foreign key checks are temporarily disabled using database-specific commands for SQLite and PostgreSQL to avoid constraint violations while dropping tables. After the tables are recreated, the function re-enables the foreign key checks and commits the changes. It then removes the existing Alembic migration directory, recreates it, and reinitializes Alembic to start with a fresh migration history.
    
    Raises:
        Exception: Re-raises any exception encountered during the reset process (after rolling back if needed), ensuring that errors are logged before the reset is terminated.
    
    Side Effects:
        - Drops all database tables and the Alembic version table.
        - Recreates database tables according to current SQLAlchemy metadata.
        - Removes and reinitializes the Alembic migration directory.
        - Logs the progress and any errors encountered during the reset.
    """
    logger.log("DATABASE", "Starting Hard Reset of Database")

    # Disable foreign key checks temporarily
    with db.engine.connect() as connection:
        if db.engine.name == "sqlite":
            connection.execute(text("PRAGMA foreign_keys = OFF"))
        elif db.engine.name == "postgresql":
            connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))

        try:
            for table in reversed(db.Model.metadata.sorted_tables):
                try:
                    table.drop(connection, checkfirst=True)
                    logger.log("DATABASE", f"Dropped table: {table.name}")
                except Exception as e:
                    logger.log("DATABASE", f"Error dropping table {table.name}: {str(e)}")

            try:
                connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
                logger.log("DATABASE", "Alembic version table dropped")
            except Exception as e:
                logger.log("DATABASE", f"Error dropping alembic_version table: {str(e)}")

            db.Model.metadata.create_all(connection)
            logger.log("DATABASE", "All tables recreated")

            # Re-enable foreign key checks
            if db.engine.name == "sqlite":
                connection.execute(text("PRAGMA foreign_keys = ON"))
            elif db.engine.name == "postgresql":
                connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

            connection.commit()
        except Exception as e:
            connection.rollback()
            logger.log("DATABASE", f"Error during database reset: {str(e)}")
            raise

    try:
        alembic_dir = root_dir / "data" / "alembic"
        logger.log("DATABASE", "Removing Alembic Directory")
        shutil.rmtree(alembic_dir, ignore_errors=True)
        os.makedirs(alembic_dir, exist_ok=True)
        alembic.init(alembic_dir)
        logger.log("DATABASE", "Alembic reinitialized")
    except Exception as e:
        logger.log("DATABASE", f"Error reinitializing Alembic: {str(e)}")

    logger.log("DATABASE", "Pre Migration - Hard Reset Complete")

# Hard Reset Database
reset = os.getenv("HARD_RESET", None)
if reset is not None and reset.lower() in ["true","1"]:
    hard_reset_database()
    exit(0)

# Hard Reset Database
reset = os.getenv("HARD_RESET_PRE_MIGRATION", None)
if reset is not None and reset.lower() in ["true","1"]:
    hard_reset_database_pre_migration()
    exit(0)

# Repair Symlinks
if os.getenv("REPAIR_SYMLINKS", None) is not None and os.getenv("REPAIR_SYMLINKS").lower() in ["true","1"]:
    fix_broken_symlinks(settings_manager.settings.symlink.library_path, settings_manager.settings.symlink.rclone_path)
    exit(0)
